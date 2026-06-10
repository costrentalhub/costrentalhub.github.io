import re
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from cost_rental_alerts.addresses import compose_address
from cost_rental_alerts.models import Listing
from cost_rental_alerts.scrapers.common import (
    fetch,
    normalize_status,
    parse_bed_count,
    parse_income_amount,
)

LDA_URL = "https://lda.ie/affordable-homes/lda-cost-rental/"


@dataclass
class LdaDetail:
    bedrooms: str | None = None
    price_from: float | None = None
    quantity: int | None = None
    income_min: float | None = None
    income_max: float | None = None
    applications_close_at: str | None = None


def _slug_from_url(url: str) -> str:
    path = urlparse(url).path.rstrip("/")
    return path.split("/")[-1]


def _beds_from_property_type(text: str) -> int | None:
    if "studio" in text.lower():
        return 0
    return parse_bed_count(text)


def _bedrooms_label(counts: list[int]) -> str | None:
    if not counts:
        return None
    nums = sorted(set(counts))
    if nums == [0]:
        return "studio"
    if 0 in nums:
        upper = max(n for n in nums if n > 0)
        return f"studio-{upper} bed"
    if len(nums) == 1:
        return f"{nums[0]} bed"
    return f"{nums[0]}-{nums[-1]} bed"


def _is_eligibility_table(headers: list[str]) -> bool:
    joined = " ".join(headers).lower()
    return "maximum" in joined and any(
        token in joined for token in ("minimum", "apartment type", "property type")
    )


def _column_indexes(headers: list[str]) -> dict[str, int | None]:
    lowered = [header.lower() for header in headers]

    def find_type_col() -> int:
        for index, header in enumerate(lowered):
            if "apartment type" in header or "property type" in header:
                return index
        return 0

    def find_min_col() -> int | None:
        for index, header in enumerate(lowered):
            if "minimum" in header:
                return index
        return None

    def find_max_col() -> int | None:
        for index, header in enumerate(lowered):
            if "maximum" in header:
                return index
        return None

    return {
        "type": find_type_col(),
        "min": find_min_col(),
        "max": find_max_col(),
    }


def _parse_eligibility_table(soup: BeautifulSoup) -> tuple[list[int], list[float], list[float]]:
    bed_counts: list[int] = []
    income_mins: list[float] = []
    income_maxes: list[float] = []

    for table in soup.select("table"):
        rows = table.select("tr")
        if len(rows) < 2:
            continue

        headers = [
            cell.get_text(strip=True)
            for cell in (rows[0].select("th") or rows[0].select("td"))
        ]
        if not _is_eligibility_table(headers):
            continue

        cols = _column_indexes(headers)
        for row in rows[1:]:
            cells = [cell.get_text(strip=True) for cell in row.select("td")]
            if len(cells) < 2:
                continue

            type_col = cols["type"]
            if type_col < len(cells):
                bed_count = _beds_from_property_type(cells[type_col])
                if bed_count is not None:
                    bed_counts.append(bed_count)

            min_col = cols["min"]
            if min_col is not None and min_col < len(cells):
                amount = parse_income_amount(cells[min_col])
                if amount is not None:
                    income_mins.append(amount)

            max_col = cols["max"]
            if max_col is not None and max_col < len(cells):
                amount = parse_income_amount(cells[max_col])
                if amount is not None:
                    income_maxes.append(amount)

        if bed_counts or income_mins or income_maxes:
            break

    return bed_counts, income_mins, income_maxes


def _parse_monthly_rents(html: str) -> list[float]:
    rents: list[float] = []
    for match in re.finditer(
        r"€\s*([0-9][0-9,]*)\s+per calendar month",
        html,
        re.IGNORECASE,
    ):
        rents.append(float(match.group(1).replace(",", "")))
    return rents


_MONTH = (
    r"(January|February|March|April|May|June|July|August|September|"
    r"October|November|December)"
)


def _parse_close_at(html: str) -> str | None:
    """
    Parse the application close date from the notice near the top of the page.

    Must not scan the full HTML — FAQ sections mention '30 March 2011' (policy doc).
    """
    header = re.search(
        r"registrations clos(?:e|ed) at\s*(.{0,220})",
        html,
        re.IGNORECASE,
    )
    if not header:
        return None

    snippet = header.group(1)
    day: str | None = None
    month_name: str | None = None
    year: str | None = None

    day_month = re.search(
        rf"(\d{{1,2}})(?:st|nd|rd|th)?(?:\s+of)?\s+{_MONTH},?\s+(\d{{4}})",
        snippet,
        re.IGNORECASE,
    )
    if day_month:
        day, month_name, year = day_month.groups()
    else:
        month_day = re.search(
            rf"{_MONTH}\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})",
            snippet,
            re.IGNORECASE,
        )
        if not month_day:
            return None
        month_name, day, year = month_day.groups()
    year_int = int(year)
    if year_int < 2020 or year_int > datetime.now().year + 2:
        return None
    try:
        month = datetime.strptime(month_name[:3], "%b").month
        return f"{year}-{month:02d}-{int(day):02d}"
    except ValueError:
        return None


def _parse_detail(html: str) -> LdaDetail:
    soup = BeautifulSoup(html, "html.parser")
    bed_counts, income_mins, income_maxes = _parse_eligibility_table(soup)
    monthly_rents = _parse_monthly_rents(html)

    bedrooms = _bedrooms_label(bed_counts)
    if bedrooms is None:
        text = soup.get_text(" ", strip=True)
        bed_match = re.search(
            r"(One|Two|Three|Four|1|2|3|4)[-\s]?bed(?:room)?\s+"
            r"(?:house|apartment|duplex|townhouse)",
            text,
            re.I,
        )
        if bed_match:
            word = bed_match.group(1).lower()
            mapping = {"one": 1, "two": 2, "three": 3, "four": 4}
            num = mapping.get(word, word)
            bedrooms = f"{num} bed"

    # Only trust explicit monthly rent phrases — avoid picking income caps (€66,000).
    price_from = min(monthly_rents) if monthly_rents else None

    quantity = len(bed_counts) if bed_counts else None

    return LdaDetail(
        bedrooms=bedrooms,
        price_from=price_from,
        quantity=quantity,
        income_min=min(income_mins) if income_mins else None,
        income_max=max(income_maxes) if income_maxes else None,
        applications_close_at=_parse_close_at(html),
    )


def _enrich_listings(listings: list[Listing]) -> None:
    for listing in listings:
        try:
            detail_html = fetch(listing.url)
            detail = _parse_detail(detail_html)
            listing.bedrooms = detail.bedrooms
            listing.price_from = detail.price_from
            listing.quantity = detail.quantity
            listing.income_min = detail.income_min
            listing.income_max = detail.income_max
            listing.applications_close_at = detail.applications_close_at
            listing.address = compose_address(
                listing.title,
                listing.location,
                page_html=detail_html,
            )
        except Exception:
            continue


def scrape_lda() -> list[Listing]:
    html = fetch(LDA_URL)
    soup = BeautifulSoup(html, "html.parser")
    listings: list[Listing] = []
    seen = set()

    for card in soup.select("div.card.cost-rental-card"):
        link = card.select_one('a[href*="/lda-cost-rental/"]')
        if not link:
            continue

        url = link.get("href", "").strip()
        if url.endswith("/lda-cost-rental") or url.endswith("/lda-cost-rental/"):
            continue

        slug = _slug_from_url(url)
        listing_id = f"lda:{slug}"
        if listing_id in seen:
            continue
        seen.add(listing_id)

        classes = card.get("class", [])
        status = "open" if "open" in classes else "closed" if "closed" in classes else "unknown"

        label = card.select_one("div.scheme-label")
        if label:
            status = normalize_status(label.get_text())

        title_el = card.select_one("h2.affordable-heading")
        title = title_el.get_text(strip=True) if title_el else slug.replace("-", " ").title()

        card_text = card.select_one("div.card-text")
        if card_text and status == "unknown":
            status = normalize_status(card_text.get_text())

        listings.append(
            Listing(
                id=listing_id,
                source="lda",
                title=title,
                location=title,
                url=url,
                status=status,
                category="rent",
            )
        )

    _enrich_listings(listings)
    return listings
