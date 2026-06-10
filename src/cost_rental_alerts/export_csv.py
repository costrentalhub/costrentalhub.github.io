#!/usr/bin/env python3
"""Export listings.db to CSV files."""

import csv
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from cost_rental_alerts.locations import format_city_neighborhood
from cost_rental_alerts.paths import DATA_DIR

TZ = ZoneInfo("Europe/Dublin")
OPENING_SOON_DAYS = 14

DB_PATH = DATA_DIR / "listings.db"
OUT_PATH = DATA_DIR / "listings-export.csv"
OPEN_OUT_PATH = DATA_DIR / "listings-open.csv"

CSV_HEADERS = [
    "name",
    "location",
    "address",
    "price",
    "quantity",
    "beds",
    "status",
    "income_min",
    "income_max",
    "listed_at",
    "open_on",
    "close_on",
    "source",
    "link",
]

SELECT_SQL = """
    SELECT title, location, address, price_from, quantity, bedrooms, status,
           income_min, income_max,
           listed_at, applications_open_at, applications_close_at, source, url
    FROM listings WHERE category = 'rent'
"""


def fmt_date(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        return datetime.strptime(iso[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return iso


def fmt_price(price: float | None) -> str:
    if price is None:
        return ""
    if float(price) == int(price):
        return str(int(price))
    s = f"{float(price):.2f}".rstrip("0").rstrip(".")
    return s.replace(".", ",")


def fmt_beds(bedrooms: str | None) -> str:
    if not bedrooms:
        return ""
    return bedrooms.removesuffix(" bed").strip()


def resolve_export_status(
    status: str | None,
    applications_open_at: str | None,
    *,
    today: date | None = None,
) -> str:
    """Map stored scraper status to CSV values: open, closed, opening soon."""
    if status == "open":
        return "open"
    if status in ("opening soon", "coming_soon", "opening_soon"):
        return "opening soon"

    ref = today or datetime.now(TZ).date()
    if applications_open_at:
        try:
            open_at = date.fromisoformat(applications_open_at[:10])
        except ValueError:
            open_at = None
        else:
            soon_end = ref + timedelta(days=OPENING_SOON_DAYS)
            if ref < open_at <= soon_end:
                return "opening soon"

    return "closed"


def _write_rows(path: Path, rows) -> int:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(CSV_HEADERS)
        for (
            title,
            location,
            address,
            price,
            quantity,
            bedrooms,
            status,
            income_min,
            income_max,
            listed,
            open_,
            close,
            source,
            url,
        ) in rows:
            writer.writerow(
                [
                    title,
                    format_city_neighborhood(title, location or ""),
                    address or "",
                    fmt_price(price),
                    quantity if quantity is not None else "",
                    fmt_beds(bedrooms),
                    resolve_export_status(status, open_),
                    fmt_price(income_min),
                    fmt_price(income_max),
                    fmt_date(listed),
                    fmt_date(open_),
                    fmt_date(close),
                    source,
                    url or "",
                ]
            )
    return len(rows)


def export_csv() -> int:
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        SELECT_SQL + " ORDER BY lower(title), source"
    ).fetchall()
    return _write_rows(OUT_PATH, rows)


def export_open_csv() -> int:
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        SELECT_SQL + " AND status = 'open' ORDER BY lower(title), source"
    ).fetchall()
    return _write_rows(OPEN_OUT_PATH, rows)


def export_all() -> tuple[int, int]:
    return export_csv(), export_open_csv()


if __name__ == "__main__":
    total, open_count = export_all()
    print(f"Wrote {total} rows to {OUT_PATH}")
    print(f"Wrote {open_count} rows to {OPEN_OUT_PATH}")
