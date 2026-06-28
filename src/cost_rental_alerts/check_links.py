#!/usr/bin/env python3
"""Check HTTP status of scheme source links exported in CSV."""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from pathlib import Path

import requests

from cost_rental_alerts.notify import format_broken_links_alert, send_ops_alert
from cost_rental_alerts.paths import DATA_DIR

CSV_PATH = DATA_DIR / "listings-export.csv"
ACTIVE_STATUSES = {"open", "opening soon"}
USER_AGENT = "CostRentalAlerts-LinkCheck/1.0"


@dataclass
class LinkFailure:
    name: str
    source: str
    url: str
    status: int
    detail: str


def active_scheme_links(csv_path: Path = CSV_PATH) -> list[tuple[str, str, str]]:
    """Return (name, source, url) for open and opening-soon rows."""
    links: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str]] = set()

    with csv_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            status = (row.get("status") or "").strip().casefold()
            if status not in ACTIVE_STATUSES:
                continue
            name = (row.get("name") or "").strip()
            source = (row.get("source") or "").strip()
            url = (row.get("link") or "").strip()
            if not url:
                continue
            key = (source, url)
            if key in seen:
                continue
            seen.add(key)
            links.append((name, source, url))

    return links


def check_url(url: str, *, timeout: int = 20) -> tuple[int, str]:
    headers = {"User-Agent": USER_AGENT}
    try:
        response = requests.head(
            url,
            allow_redirects=True,
            timeout=timeout,
            headers=headers,
        )
        if response.status_code in {405, 501} or response.status_code >= 400:
            response = requests.get(
                url,
                allow_redirects=True,
                timeout=timeout,
                headers=headers,
            )
        return response.status_code, response.reason or "OK"
    except requests.RequestException as exc:
        return 0, str(exc)


def find_broken_links(csv_path: Path = CSV_PATH) -> list[LinkFailure]:
    failures: list[LinkFailure] = []
    for name, source, url in active_scheme_links(csv_path):
        status, detail = check_url(url)
        if status >= 400 or status == 0:
            failures.append(
                LinkFailure(name=name, source=source, url=url, status=status, detail=detail)
            )
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check scheme source links for HTTP errors")
    parser.add_argument(
        "--csv",
        type=Path,
        default=CSV_PATH,
        help="CSV export to read links from",
    )
    parser.add_argument(
        "--warn-only",
        action="store_true",
        help="Always exit 0; print failures as warnings",
    )
    parser.add_argument(
        "--no-alert",
        action="store_true",
        help="Do not send ops email for broken links",
    )
    args = parser.parse_args(argv)

    failures = find_broken_links(args.csv)
    if failures:
        print(format_broken_links_alert(failures))
        if not args.no_alert:
            send_ops_alert(format_broken_links_alert(failures))
    else:
        print("All active scheme links responded OK.")

    return 0 if (args.warn_only or not failures) else 1


if __name__ == "__main__":
    raise SystemExit(main())
