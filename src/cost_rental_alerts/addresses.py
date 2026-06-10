"""Build Google Maps–compatible address strings from listing data."""

import html
import re
from urllib.parse import unquote

from cost_rental_alerts.locations import normalize_location

_ROAD_RE = re.compile(
    r"\b(Road|Rd|Street|St|Avenue|Ave|Lane|Drive|Dr|Way|Court|Close|Parade|Highway)\b",
    re.I,
)
_COUNTY_RE = re.compile(r"Co\.\s*\w+", re.I)


def _clean(text: str) -> str:
    return html.unescape(re.sub(r"\s+", " ", text).strip())


def _ensure_ireland(addr: str) -> str:
    if not addr:
        return ""
    if not re.search(r"\bIreland\b", addr, re.I):
        addr = addr.rstrip(", ") + ", Ireland"
    return addr


def _merge_parts(*chunks: str) -> str:
    parts: list[str] = []
    seen: set[str] = set()
    for chunk in chunks:
        if not chunk:
            continue
        for part in chunk.split(","):
            piece = _clean(part)
            if not piece:
                continue
            key = piece.lower()
            if key in seen:
                continue
            seen.add(key)
            parts.append(piece)
    return ", ".join(parts)


_COORD_RE = re.compile(r"^-?\d+(?:\.\d+)?,-?\d+(?:\.\d+)?$")


def _is_usable_maps_address(addr: str) -> bool:
    if not addr or _COORD_RE.match(addr):
        return False
    # Single token (e.g. "Harpur Lane") is too vague — prefer title/location merge.
    return "," in addr


def parse_google_maps_link(page_html: str) -> str | None:
    """Extract destination from embedded Google Maps directions/place links."""
    for match in re.finditer(
        r'href="(https?://(?:www\.)?google\.com/maps[^"]+)"',
        page_html,
    ):
        link = match.group(1)
        for pattern in (r"/dir//([^/@]+)", r"/place/([^/@]+)"):
            found = re.search(pattern, link)
            if found:
                addr = _clean(unquote(found.group(1).replace("+", " ")))
                if _is_usable_maps_address(addr):
                    return _ensure_ireland(addr)
    return None


def parse_situated_off(page_html: str) -> str | None:
    match = re.search(
        r"situated off\s+([^.<]+?)(?:\s+connecting|\s+in\s|,|\.)",
        page_html,
        re.I,
    )
    return _clean(match.group(1)) if match else None


def _title_has_street(title: str) -> bool:
    return bool(_ROAD_RE.search(title))


def compose_address(
    title: str,
    location: str,
    *,
    detail_location: str | None = None,
    page_html: str | None = None,
) -> str:
    """
    Return a comma-separated address suitable for pasting into Google Maps.

    Priority: Maps link > street in prose > detail Location > title + location.
    """
    title = _clean(title)
    location = normalize_location(_clean(location or ""))
    detail_location = (
        normalize_location(_clean(detail_location)) if detail_location else ""
    )

    if page_html:
        maps_addr = parse_google_maps_link(page_html)
        if maps_addr:
            return maps_addr

        street = parse_situated_off(page_html)
        if street:
            area = _merge_parts(title, detail_location or location)
            if area:
                return _ensure_ireland(f"{street}, {area}")
            return _ensure_ireland(street)

    if detail_location:
        if _title_has_street(title):
            merged = _merge_parts(title, detail_location)
        else:
            scheme = title.split("/")[0].split(",")[0].strip()
            if scheme and scheme.lower() not in detail_location.lower():
                merged = _merge_parts(scheme, detail_location)
            else:
                merged = detail_location
        return _ensure_ireland(merged)

    if _title_has_street(title) or "," in title:
        merged = _merge_parts(title, location)
        return _ensure_ireland(merged)

    merged = _merge_parts(title, location)
    return _ensure_ireland(merged)
