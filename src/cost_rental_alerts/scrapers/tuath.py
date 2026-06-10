import re
from datetime import datetime
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from cost_rental_alerts.addresses import compose_address
from cost_rental_alerts.locations import normalize_location
from cost_rental_alerts.models import Listing
from cost_rental_alerts.scrapers.common import (
    bedrooms_range,
    fetch,
    normalize_status,
    parse_bed_count,
    parse_price,
)

TUATH_URL = "https://tuathhousing.ie/cost-rental/"
TZ = ZoneInfo("Europe/Dublin")

_MONTH = (
    r"(January|February|March|April|May|June|July|August|September|"
    r"October|November|December)"
)
_WEEKDAY = (
    r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s*"
)


def _slug_from_url(url: str) -> str:
    path = urlparse(url).path.rstrip("/")
    return path.split("/")[-1]


def _header_indexes(headers: list[str]) -> dict[str, int | None]:
    def find(*needles: str) -> int | None:
        for needle in needles:
            for index, header in enumerate(headers):
                if needle in header:
                    return index
        return None

    return {
        "rent": find("cost rent"),
        "quantity": find("number of homes"),
    }


def _resolve_year(day: int, month: int, *, prefer_future: bool) -> int:
    today = datetime.now(TZ).date()
    year = today.year
    candidate = datetime(year, month, day).date()
    if prefer_future and candidate < today:
        return year + 1
    return year


def _parse_close_at(html: str, *, prefer_future: bool = True) -> str | None:
    """
    Parse 'Application closing date is Thursday, 11 June at 2PM.' from detail HTML.

    Year is omitted on Tuath pages — infer from listing status and today's date.
    """
    header = re.search(
        r"application closing date is\s*(.{0,120})",
        html,
        re.IGNORECASE,
    )
    if not header:
        return None

    snippet = re.sub(r"<[^>]+>", " ", header.group(1))
    snippet = re.sub(r"\s+", " ", snippet).strip()

    match = re.search(
        rf"{_WEEKDAY}?(\d{{1,2}})(?:st|nd|rd|th)?\s+{_MONTH}"
        rf"(?:\s+(\d{{4}}))?(?:\s+at\b|[.<]|$)",
        snippet,
        re.IGNORECASE,
    )
    if not match:
        return None

    day, month_name, year = match.groups()
    try:
        month = datetime.strptime(month_name[:3], "%b").month
        day_int = int(day)
    except ValueError:
        return None

    if year:
        year_int = int(year)
        if year_int < 2020 or year_int > datetime.now(TZ).year + 2:
            return None
    else:
        year_int = _resolve_year(day_int, month, prefer_future=prefer_future)

    return f"{year_int}-{month:02d}-{day_int:02d}"


def _parse_unit_table(html: str) -> tuple[str | None, float | None, int | None]:
    """Return (bedrooms range, min price, total homes) from the property table."""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("table")
    if not table:
        return None, None, None

    rows = table.select("tr")
    if len(rows) < 2:
        return None, None, None

    header_cells = rows[0].select("th") or rows[0].select("td")
    headers = [cell.get_text(strip=True).lower() for cell in header_cells]
    cols = _header_indexes(headers)

    bed_counts: list[int] = []
    prices: list[float] = []
    quantities: list[int] = []

    for row in rows[1:]:
        cells = [cell.get_text(strip=True) for cell in row.select("td")]
        if len(cells) < 2:
            continue

        bed_count = parse_bed_count(cells[0])
        if bed_count is not None:
            bed_counts.append(bed_count)

        rent_col = cols["rent"]
        if rent_col is not None and rent_col < len(cells):
            price = parse_price(cells[rent_col])
            if price is not None:
                prices.append(price)

        qty_col = cols["quantity"]
        if qty_col is not None and qty_col < len(cells):
            qty_match = re.match(r"(\d+)", cells[qty_col])
            if qty_match:
                quantities.append(int(qty_match.group(1)))

    bedrooms = bedrooms_range(bed_counts)
    price_from = min(prices) if prices else None
    quantity = sum(quantities) if quantities else None
    return bedrooms, price_from, quantity


def _enrich_listings(listings: list[Listing]) -> None:
    for listing in listings:
        try:
            detail_html = fetch(listing.url)
            bedrooms, price_from, quantity = _parse_unit_table(detail_html)
            close_at = _parse_close_at(
                detail_html,
                prefer_future=listing.status == "open",
            )
            listing.bedrooms = bedrooms
            listing.price_from = price_from
            listing.quantity = quantity
            listing.address = compose_address(
                listing.title,
                listing.location,
                page_html=detail_html,
            )
            if close_at:
                listing.applications_close_at = close_at
        except Exception:
            continue


def scrape_tuath() -> list[Listing]:
    html = fetch(TUATH_URL)
    soup = BeautifulSoup(html, "html.parser")
    listings: list[Listing] = []
    seen = set()

    for box in soup.select("div.property-box"):
        title_el = box.select_one("h3")
        link_el = box.select_one("a.view-btn")
        if not title_el or not link_el:
            continue

        title = title_el.get_text(strip=True)
        url = link_el.get("href", "").strip()
        slug = _slug_from_url(url)
        listing_id = f"tuath:{slug}"
        if listing_id in seen:
            continue
        seen.add(listing_id)

        tag_el = box.select_one("div.property-tag")
        status = normalize_status(tag_el.get_text()) if tag_el else "unknown"

        location_el = box.select_one("div.property-info p")
        location = ""
        if location_el:
            location = normalize_location(
                re.sub(r"\s+", " ", location_el.get_text(" ", strip=True))
            )

        listings.append(
            Listing(
                id=listing_id,
                source="tuath",
                title=title,
                location=location,
                url=url,
                status=status,
                category="rent",
            )
        )

    _enrich_listings(listings)
    return listings
