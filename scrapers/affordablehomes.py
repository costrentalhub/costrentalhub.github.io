import re
from datetime import datetime
from typing import Dict, List, Tuple
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from addresses import compose_address
from models import Listing
from scrapers.common import (
    fetch,
    normalize_bedrooms,
    normalize_status,
    parse_listed_date,
    parse_price,
    parse_quantity,
)

BASE_URL = "https://affordablehomes.ie"
RENT_URL = f"{BASE_URL}/rent/"
CALENDAR_URL = f"{BASE_URL}/rent/calendar/"


def _calendar_events(html: str) -> Dict[str, Dict[str, str]]:
    """Map slug -> {opened_at, closed_at} from calendar page (YYYY-MM-DD)."""
    soup = BeautifulSoup(html, "html.parser")
    events: Dict[str, Dict[str, str]] = {}
    year = datetime.now().year

    for article in soup.select("article.calendar"):
        day_el = article.select_one("h4 span")
        month_el = article.select_one("h4 span.fwb")
        if not day_el or not month_el:
            continue
        try:
            day = int(day_el.get_text(strip=True))
            month_name = month_el.get_text(strip=True)
            month = datetime.strptime(month_name, "%b").month
            event_date = f"{year}-{month:02d}-{day:02d}"
        except ValueError:
            continue

        for block in article.select("div.open, div.close"):
            classes = block.get("class", [])
            if "open" in classes:
                event_type = "opened_at"
            elif "close" in classes:
                event_type = "closed_at"
            else:
                continue

            for link in block.select('a[href^="/rent/"]'):
                href = link.get("href", "")
                slug_match = re.search(r"/rent/([^/]+)/", href)
                if not slug_match:
                    continue
                slug = slug_match.group(1)
                bucket = events.setdefault(slug, {})
                bucket[event_type] = event_date

    return events


def _parse_listing_page(html: str) -> List[Listing]:
    soup = BeautifulSoup(html, "html.parser")
    listings: List[Listing] = []

    for article in soup.select("article.property"):
        classes = article.get("class", [])
        status = "open" if "open" in classes else "closed" if "closed" in classes else "unknown"

        title_link = article.select_one("h3 a")
        if not title_link:
            continue

        slug = title_link.get("href", "").strip("/")
        title = title_link.get_text(strip=True)
        url = urljoin(RENT_URL, slug + "/")

        price_el = article.select_one("p.price")
        price = parse_price(price_el.get_text()) if price_el else None

        status_el = article.select_one("p.status")
        if status_el:
            status = normalize_status(status_el.get_text())

        location_el = article.select_one("p.location span")
        location = location_el.get_text(strip=True) if location_el else ""

        listed_el = article.select_one("p.date")
        listed_at = (
            parse_listed_date(listed_el.get_text())
            if listed_el
            else None
        )

        listings.append(
            Listing(
                id=f"affordablehomes:{slug}",
                source="affordablehomes",
                title=title,
                location=location,
                url=url,
                status=status,
                category="rent",
                price_from=price,
                listed_at=listed_at,
            )
        )

    return listings


def _detail_field(soup: BeautifulSoup, label: str) -> str | None:
    for h3 in soup.select("h3.fwu"):
        if h3.get_text(strip=True) == label:
            sibling = h3.find_next_sibling("p")
            if sibling:
                return sibling.get_text(strip=True)
    return None


def _parse_detail(html: str) -> tuple[str | None, int | None, str | None, str | None]:
    """Return (bedrooms, quantity, applications_close_at ISO date, detail location)."""
    soup = BeautifulSoup(html, "html.parser")

    bedrooms = None
    raw_beds = _detail_field(soup, "Bedrooms")
    if raw_beds:
        bedrooms = normalize_bedrooms(raw_beds)

    quantity = None
    raw_qty = _detail_field(soup, "Availability")
    if raw_qty:
        quantity = parse_quantity(raw_qty)

    detail_location = _detail_field(soup, "Location")

    close_match = re.search(
        r"Applications Close:.*?(\d{1,2})\s+(\w+)\s+(\d{4})",
        html,
        re.IGNORECASE | re.DOTALL,
    )
    close_at = None
    if close_match:
        day, month_name, year = close_match.groups()
        try:
            month = datetime.strptime(month_name[:3], "%b").month
            close_at = f"{year}-{month:02d}-{int(day):02d}"
        except ValueError:
            pass

    return bedrooms, quantity, close_at, detail_location


def _enrich_listings(listings: List[Listing]) -> None:
    for listing in listings:
        try:
            detail_html = fetch(listing.url)
            bedrooms, quantity, close_at, detail_location = _parse_detail(detail_html)
            listing.bedrooms = bedrooms
            listing.quantity = quantity
            listing.address = compose_address(
                listing.title,
                listing.location,
                detail_location=detail_location,
                page_html=detail_html,
            )
            if listing.status == "open" and close_at:
                listing.applications_close_at = close_at
        except Exception:
            continue


def _total_pages(html: str) -> int:
    match = re.search(r"Showing \d+ to \d+ of (\d+)", html)
    if not match:
        return 1
    total = int(match.group(1))
    return max(1, (total + 11) // 12)


def scrape_affordablehomes() -> List[Listing]:
    first_html = fetch(RENT_URL)
    pages = _total_pages(first_html)
    listings: List[Listing] = []
    seen_ids = set()

    for page in range(1, pages + 1):
        html = first_html if page == 1 else fetch(f"{RENT_URL}?page={page}")
        for listing in _parse_listing_page(html):
            if listing.id not in seen_ids:
                seen_ids.add(listing.id)
                listings.append(listing)

    try:
        calendar_html = fetch(CALENDAR_URL)
        events = _calendar_events(calendar_html)
    except Exception:
        events = {}

    for listing in listings:
        slug = listing.id.split(":", 1)[1]
        if slug not in events:
            continue
        if events[slug].get("opened_at"):
            listing.applications_open_at = events[slug]["opened_at"]
        # Only use calendar close dates for open listings (avoid stale dates on old closed schemes)
        if listing.status == "open" and events[slug].get("closed_at"):
            listing.applications_close_at = events[slug]["closed_at"]

    _enrich_listings(listings)
    return listings
