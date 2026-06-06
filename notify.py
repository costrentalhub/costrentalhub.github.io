import os
import urllib.parse
from datetime import date, datetime
from typing import List
from zoneinfo import ZoneInfo

import requests

from diff import NewsItem

TZ = ZoneInfo("Europe/Dublin")


def _today() -> date:
    return datetime.now(TZ).date()


def _format_price(price: float | None, prefix: str = "from") -> str:
    if price is None:
        return ""
    if price == int(price):
        amount = f"€{int(price):,}/mo"
    else:
        amount = f"€{price:,.2f}/mo"
    return f"{prefix} {amount}" if prefix else amount


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _format_open_date_short(value: str | None) -> str:
    parsed = _parse_date(value)
    if not parsed:
        return ""
    return parsed.strftime("%d/%m/%y")


def _closes_line(close_at: str | None) -> str:
    close_date = _parse_date(close_at)
    if not close_date:
        return "Closes in: not informed"
    delta = (close_date - _today()).days
    if delta < 0:
        return "Closes in: not informed"
    if delta == 0:
        return "Closes today"
    if delta == 1:
        return "Closes in 1 day"
    return f"Closes in {delta} days"


def _format_details_line(bedrooms: str | None, price: float | None) -> str:
    parts = []
    if bedrooms:
        parts.append(f"🛏️ {bedrooms}")
    price_text = _format_price(price)
    if price_text:
        parts.append(f"💰 {price_text}")
    return " | ".join(parts)


def _format_listing_block(
    index: int,
    title: str,
    location: str,
    url: str,
    bedrooms: str | None,
    price: float | None,
    *,
    extra_line: str | None = None,
) -> List[str]:
    loc = location or title
    lines = [f"{index}. {title} — {loc}"]
    details = _format_details_line(bedrooms, price)
    if details:
        lines.append(f"   {details}")
    if extra_line:
        lines.append(f"   {extra_line}")
    lines.append(f"   {url}")
    lines.append("")
    return lines


SOURCE_PRIORITY = {"affordablehomes": 0, "lda": 1, "tuath": 2}


def _pick_better_item(current: NewsItem, candidate: NewsItem) -> NewsItem:
    """Same scheme phase on multiple sources — prefer open, then affordablehomes."""
    if current.status == "open" and candidate.status != "open":
        return current
    if candidate.status == "open" and current.status != "open":
        return candidate
    if SOURCE_PRIORITY.get(candidate.source, 9) < SOURCE_PRIORITY.get(current.source, 9):
        return candidate
    return current


def _dedupe_news(items: List[NewsItem]) -> List[NewsItem]:
    """Merge only the same scheme phase (name + open date), not different phases."""
    best: dict[str, NewsItem] = {}
    for item in items:
        key = item.scheme_key or item.listing_id
        current = best.get(key)
        if current is None:
            best[key] = item
        else:
            best[key] = _pick_better_item(current, item)
    return list(best.values())


def format_message(news: List[NewsItem], total_scraped: int) -> str:
    today = datetime.now(TZ).strftime("%d/%m/%Y")
    lines = [f"🏠 Cost Rental Alert — {today}", ""]

    if not news:
        lines.append("✅ No updates today.")
        lines.append(f"({total_scraped} schemes monitored)")
        return "\n".join(lines)

    news = _dedupe_news(news)
    opened = [n for n in news if n.notification_type in ("new_open", "opened_today")]
    soon = [n for n in news if n.notification_type == "opening_soon"]

    if opened:
        lines.append(f"📢 APPLICATIONS OPEN ({len(opened)}):")
        lines.append("")
        for i, item in enumerate(opened, 1):
            lines.extend(
                _format_listing_block(
                    i,
                    item.title,
                    item.location,
                    item.url,
                    item.bedrooms,
                    item.price_from,
                    extra_line=_closes_line(item.applications_close_at),
                )
            )

    if soon:
        lines.append(f"📅 OPENING SOON ({len(soon)}):")
        lines.append("")
        for i, item in enumerate(soon, 1):
            open_date = _format_open_date_short(item.applications_open_at)
            extra = f"Opens: {open_date}" if open_date else None
            lines.extend(
                _format_listing_block(
                    i,
                    item.title,
                    item.location,
                    item.url,
                    item.bedrooms,
                    item.price_from,
                    extra_line=extra,
                )
            )

    lines.append(f"({total_scraped} schemes monitored)")
    return "\n".join(lines).strip()


def format_test_message(
    source_results,
    total_scraped: int,
    whatsapp_configured: bool,
) -> str:
    today = datetime.now(TZ).strftime("%d/%m/%Y")
    lines = [
        f"🧪 TEST — Cost Rental Alert — {today}",
        "",
        "Connection check:",
        "",
    ]

    for result in source_results:
        if result.ok:
            lines.append(f"✅ {result.label} — {result.count} schemes")
        else:
            lines.append(f"❌ {result.label} — ERROR")
            lines.append(f"   {result.error}")

    lines.append("")
    if whatsapp_configured:
        lines.append("✅ WhatsApp CallMeBot — credentials configured")
    else:
        lines.append("❌ WhatsApp CallMeBot — missing CALLMEBOT_PHONE / CALLMEBOT_APIKEY")

    samples: list = []
    for result in source_results:
        for item in result.open_samples:
            samples.append(item)
            if len(samples) >= 3:
                break
        if len(samples) >= 3:
            break

    if samples:
        lines.extend(["", f"📢 Sample open listings ({len(samples)}):"])
        for i, item in enumerate(samples, 1):
            lines.extend(
                _format_listing_block(
                    i,
                    item.title,
                    item.location,
                    item.url,
                    item.bedrooms,
                    item.price_from,
                    extra_line=_closes_line(item.applications_close_at),
                )
            )

    lines.extend(
        [
            f"Total: {total_scraped} schemes monitored",
            "Tomorrow: normal alerts (new updates only).",
        ]
    )
    return "\n".join(lines).strip()


def send_whatsapp(message: str, dry_run: bool = False) -> bool:
    phone = os.environ.get("CALLMEBOT_PHONE", "").strip()
    apikey = os.environ.get("CALLMEBOT_APIKEY", "").strip()

    if dry_run or not phone or not apikey:
        print("--- WhatsApp message (dry-run / missing credentials) ---")
        print(message)
        print("--- end ---")
        return False

    url = (
        "https://api.callmebot.com/whatsapp.php?"
        f"phone={urllib.parse.quote(phone)}"
        f"&text={urllib.parse.quote(message)}"
        f"&apikey={urllib.parse.quote(apikey)}"
    )
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    print("WhatsApp message sent.")
    return True
