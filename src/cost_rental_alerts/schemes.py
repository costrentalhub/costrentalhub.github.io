"""Logical scheme identity — distinguishes phases of the same development name."""

from collections import defaultdict

from cost_rental_alerts.models import Listing


def normalize_scheme_name(title: str) -> str:
    return " ".join(title.strip().lower().split())


def compute_scheme_key(
    title: str,
    applications_open_at: str | None,
    listed_at: str | None,
    listing_id: str,
) -> str:
    """
    Identify a scheme phase by name + open date.

    Same name + same open date across sources (e.g. Tuath + affordablehomes) = one phase.
    Different open dates or names (e.g. Parklands 2024 vs Parklands 2026) = separate entries.
    """
    name = normalize_scheme_name(title)
    open_date = applications_open_at or listed_at
    if open_date:
        return f"{name}|{open_date[:10]}"
    return f"{name}|{listing_id}"


def names_overlap(a: str, b: str) -> bool:
    na, nb = normalize_scheme_name(a), normalize_scheme_name(b)
    if na == nb:
        return True
    if na.split(",")[0].strip() == nb.split(",")[0].strip():
        return True
    shorter, longer = (na, nb) if len(na) <= len(nb) else (nb, na)
    return longer.startswith(shorter + " ") or longer.startswith(shorter + ",")


def listing_scheme_key(listing: Listing) -> str:
    return compute_scheme_key(
        listing.title,
        listing.applications_open_at,
        listing.listed_at,
        listing.id,
    )


def is_covered_by_affordablehomes(
    listing: Listing, ah_listings: list[Listing]
) -> bool:
    """True when affordablehomes already has this scheme (AH data wins)."""
    sk = listing_scheme_key(listing)
    for ah in ah_listings:
        if listing_scheme_key(ah) == sk:
            return True

    for ah in ah_listings:
        if not names_overlap(ah.title, listing.title):
            continue
        # Stale AH closed entry does not cover a new open round on LDA/Tuath.
        if listing.status == "open" and ah.status != "open":
            continue
        return True

    return False


def merge_listings_ah_first(listings: list[Listing]) -> list[Listing]:
    """Keep all AH entries; add LDA/Tuath only when not already on AH."""
    ah = [listing for listing in listings if listing.source == "affordablehomes"]
    merged = list(ah)
    for listing in listings:
        if listing.source == "affordablehomes":
            continue
        if not is_covered_by_affordablehomes(listing, ah):
            merged.append(listing)
    return merged


def enrich_cross_source_open_dates(listings: list[Listing]) -> None:
    """Copy applications_open_at from affordablehomes when another source lacks it."""
    open_dates_by_name: dict[str, list[str]] = defaultdict(list)

    for listing in listings:
        if listing.source != "affordablehomes" or not listing.applications_open_at:
            continue
        if listing.status == "open":
            open_dates_by_name[normalize_scheme_name(listing.title)].append(
                listing.applications_open_at
            )

    for listing in listings:
        if listing.applications_open_at or listing.status != "open":
            continue
        candidates = open_dates_by_name.get(normalize_scheme_name(listing.title), [])
        unique = sorted(set(candidates))
        if len(unique) == 1:
            listing.applications_open_at = unique[0]
