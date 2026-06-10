"""Format listing location as 'City - D18 Kilternan'."""

import re

_ROAD_RE = re.compile(
    r"\b(Road|Rd|Street|St|Avenue|Ave|Lane|Drive|Way|Highway|Parade)\b",
    re.I,
)
_DUBLIN_DISTRICT_RE = re.compile(r"Dublin\s+(\d{1,2})\b", re.I)
_COUNTY_RE = re.compile(r"Co\.\s*(\w+)", re.I)
_BILINGUAL_COUNTY_RE = re.compile(r"Co\.\s*na\s+[^/]+/Co\.\s*(\w+)", re.I)


def normalize_location(text: str) -> str:
    """Collapse bilingual county labels, e.g. 'Co. na Gailimhe/Co. Galway' -> 'Co. Galway'."""
    if not text:
        return ""
    cleaned = re.sub(r"\s+", " ", text.strip())
    return _BILINGUAL_COUNTY_RE.sub(r"Co. \1", cleaned)


def _county_name(text: str) -> str | None:
    bilingual = _BILINGUAL_COUNTY_RE.search(text)
    if bilingual:
        return bilingual.group(1)
    for match in _COUNTY_RE.finditer(text):
        name = match.group(1)
        if name.lower() == "na":
            continue
        return name
    return None


def _dublin_district(text: str) -> str | None:
    match = _DUBLIN_DISTRICT_RE.search(text)
    if not match:
        return None
    return f"D{int(match.group(1))}"


def _city_from_text(text: str) -> str | None:
    name = _county_name(text)
    if name:
        return "Dublin" if name.lower() == "dublin" else name
    if re.search(r"\bDublin\b", text, re.I):
        return "Dublin"
    return None


def _pick_neighborhood(parts: list[str]) -> str | None:
    candidates: list[str] = []
    for part in parts:
        if _COUNTY_RE.match(part):
            break
        if _DUBLIN_DISTRICT_RE.fullmatch(part.strip()):
            continue
        if part.strip().lower() in {"dublin", "ireland"}:
            continue
        candidates.append(part.strip())

    for part in reversed(candidates):
        if not _ROAD_RE.search(part):
            return part
    return candidates[-1] if candidates else None


def _neighborhood_from_location(location: str) -> str | None:
    if not location:
        return None
    return _pick_neighborhood([p.strip() for p in location.split(",")])


def _is_non_neighborhood_part(part: str) -> bool:
    if _DUBLIN_DISTRICT_RE.search(part):
        return True
    if re.fullmatch(r"Dublin\s+\d+.*", part, re.I):
        return True
    if re.search(r"\bPhase\s*\d+\b", part, re.I) and "," not in part:
        return True
    return False


def _neighborhood_from_title(title: str) -> str | None:
    parts = [p.strip() for p in title.split(",")]
    if len(parts) < 2:
        return None
    body = [p for p in parts[1:] if not _is_non_neighborhood_part(p)]
    if not body:
        return None
    return _pick_neighborhood(body)


def format_city_neighborhood(title: str, location: str) -> str:
    """
    Build 'City - D18 Kilternan' from title and location fields.

    Examples:
        Dun Óir, Kilternan, Dublin 18 -> Dublin - D18 Kilternan
        Folkstown Park / Balbriggan, Co. Dublin -> Dublin - Balbriggan
    """
    location = normalize_location(location or "")
    text = f"{title} {location}".strip()
    city = _city_from_text(text)
    district = _dublin_district(text)

    neighborhood = None
    if location and location.strip().lower() != title.strip().lower():
        neighborhood = _neighborhood_from_location(location)
    if not neighborhood:
        neighborhood = _neighborhood_from_title(title)

    if not city:
        city = "Ireland"

    if district and neighborhood:
        return f"{city} - {district} {neighborhood}"
    if district:
        return f"{city} - {district}"
    if neighborhood:
        return f"{city} - {neighborhood}"
    return city
