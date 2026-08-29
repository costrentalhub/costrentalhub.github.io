"""User-facing labels and canonical URLs for listing sources."""

from __future__ import annotations

SOURCE_DISPLAY: dict[str, str] = {
    "affordablehomes": "New Starter Homes",
    "lda": "LDA",
    "tuath": "Tuath Housing",
    "respond": "Respond",
    "cluid": "Clúid",
    "circle": "Circle VHA",
    "oaklee": "Oaklee",
    "chi": "CHI",
}

_AH_URL_FROM = "https://affordablehomes.ie"
_AH_URL_TO = "https://newstarterhomes.ie"


def display_source(source: str) -> str:
    key = (source or "").strip().lower()
    return SOURCE_DISPLAY.get(key, source or "Source")


def canonical_listing_url(source: str, url: str) -> str:
    if (source or "").strip().lower() != "affordablehomes" or not url:
        return url
    return url.replace(_AH_URL_FROM, _AH_URL_TO)
