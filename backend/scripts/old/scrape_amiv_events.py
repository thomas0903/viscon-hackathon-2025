from __future__ import annotations

"""
Scrape upcoming and open-registration events from https://amiv.ethz.ch/en/events
and write:
- JSON to backend/db/seed_data/events.amiv.json
- Poster URLs point to the original website (no image download)

Usage (host):
  python backend/scripts/scrape_amiv_events.py

Install deps once:
  pip install -r backend/scripts/requirements-scraper.txt

Notes
- Respects a short delay between requests.
- Dates parsed with day-first (e.g., 15/10/2025). If end time is only a clock,
  we reuse the start date and roll to next day when it crosses midnight.
- Timezone set to Europe/Zurich; stored datetimes are naive ISO strings.
"""

import json
import os
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
import os
from typing import Any, Optional
from urllib.parse import urljoin, urlparse, urlunparse, parse_qs, unquote

import requests
from bs4 import BeautifulSoup

try:
    from markdownify import markdownify as html_to_md  # type: ignore
except Exception:  # pragma: no cover
    html_to_md = None

try:
    from dateutil import parser as dateparser
    from dateutil import tz as datetz
except Exception as e:  # pragma: no cover
    raise RuntimeError("python-dateutil is required for this script") from e


BASE_URL = "https://amiv.ethz.ch"
LIST_URL = "https://amiv.ethz.ch/en/events"

# Resolve an output directory that is writable. Prefer env SCRAPER_OUT_DIR, then
# a writable db/seed_data, else fall back to var/seed_data under the app root.
def _resolve_seed_dir() -> Path:
    env_dir = os.getenv("SCRAPER_OUT_DIR", "").strip()
    if env_dir:
        p = Path(env_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p
    if Path("db/seed_data").exists() and os.access("db/seed_data", os.W_OK):
        return Path("db/seed_data")
    p = Path("var/seed_data")
    p.mkdir(parents=True, exist_ok=True)
    return p

SEED_DIR = _resolve_seed_dir()

# Always place images into app upload root
UPLOAD_ROOT = Path("var/uploads")
POSTERS_ROOT = UPLOAD_ROOT / "event" / "amiv"

OUTPUT_JSON = SEED_DIR / "events.amiv.json"
REQUEST_DELAY_SEC = float(os.getenv("SCRAPER_DELAY_SEC", "0.1"))
DEFAULT_TIMEZONE = "Europe/Zurich"
SOURCE = "amiv.ethz.ch"


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def event_id_from_url(url: str) -> Optional[str]:
    """Extract <id> from paths like /en/events/<id> or /de/events/<id>."""
    path = urlparse(url).path
    m = re.match(r"^/(en|de)/events/([^/]+)/?", path)
    if m:
        return m.group(2)
    # fallback: last non-empty segment
    parts = path.rstrip("/").split("/")
    for seg in reversed(parts):
        if seg:
            return seg
    return None


def canonical_event_url(url: str) -> str:
    u = urlparse(url)
    u = u._replace(query="", fragment="")
    # Normalize to /(en|de)/events/<id>
    m = re.match(r"^/(en|de)/events/([^/]+)/?", u.path)
    if m:
        path = f"/{m.group(1)}/events/{m.group(2)}"
        u = u._replace(path=path)
    return urlunparse(u)


def parse_dt(val: str) -> Optional[str]:
    s = (val or "").strip()
    if not s:
        return None
    try:
        tzinfos = {"CET": datetz.gettz("Europe/Zurich"), "CEST": datetz.gettz("Europe/Zurich")}
        dt = dateparser.parse(s, dayfirst=True, tzinfos=tzinfos)
        if not dt:
            return None
        # Always store naive ISO in JSON; timezone stored separately
        return dt.replace(tzinfo=None).isoformat()
    except Exception:
        return None


def to_markdown(html: str) -> str:
    if not html:
        return ""
    if html_to_md is not None:
        return html_to_md(html, heading_style="ATX")
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text("\n").strip()


def normalize_image_src(src: str) -> str:
    """AMIV uses Next.js image proxy at /_next/image?url=<real>&w=...; extract real URL."""
    if not src:
        return src
    u = urlparse(src)
    if u.path.startswith("/_next/image"):
        qs = parse_qs(u.query)
        real = qs.get("url", [""])[0]
        if real:
            real = unquote(real)
            if real.startswith("/"):
                real = urljoin(BASE_URL, real)
            return real
    if src.startswith("/"):
        return urljoin(BASE_URL, src)
    return src


def download_image(url: str, dest_dir: Path) -> Optional[str]:
    if not url:
        return None
    ensure_dir(dest_dir)
    try:
        resp = requests.get(url, timeout=20)
        if resp.status_code != 200:
            return None
        ctype = resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
        ext = {
            "image/jpeg": ".jpg",
            "image/jpg": ".jpg",
            "image/png": ".png",
            "image/webp": ".webp",
            "image/gif": ".gif",
            "image/svg+xml": ".svg",
        }.get(ctype, ".jpg")
        fname = f"poster{ext}"
        (dest_dir / fname).write_bytes(resp.content)
        return fname
    except Exception:
        return None


@dataclass
class ScrapedEvent:
    name: str
    description: Optional[str] = None
    starts_at: Optional[str] = None
    ends_at: Optional[str] = None
    timezone: Optional[str] = DEFAULT_TIMEZONE
    location_name: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    link_url: Optional[str] = None
    poster_url: Optional[str] = None
    organizer_id: Optional[int] = 1
    category: Optional[str] = None
    source: Optional[str] = SOURCE
    external_id: Optional[str] = None
    is_public: bool = True
    tags: list[str] = field(default_factory=list)

    def to_event_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_time_range(container: BeautifulSoup) -> tuple[Optional[str], Optional[str]]:
    """Parse the time block like:
    <div><span>Wednesday, 15/10/2025, 12:15</span> - <span>13:00 CEST</span></div>
    """
    start_s = None
    end_s = None
    spans = container.find_all("span") if container else []
    if len(spans) >= 2:
        start_text = spans[0].get_text(" ", strip=True)
        end_text = spans[1].get_text(" ", strip=True)
        s_iso = parse_dt(start_text)
        # If end contains a date, parse full; else combine date from start
        if re.search(r"\d{1,2}/\d{1,2}/\d{4}", end_text):
            e_iso = parse_dt(end_text)
        else:
            # Extract just HH:MM
            m = re.search(r"(\d{1,2}:\d{2})", end_text)
            if m and s_iso:
                try:
                    s_dt = dateparser.parse(s_iso)
                    e_dt = dateparser.parse(m.group(1))
                    e_dt = s_dt.replace(hour=e_dt.hour, minute=e_dt.minute, second=0, microsecond=0)
                    if e_dt < s_dt:
                        from datetime import timedelta
                        e_dt = e_dt + timedelta(days=1)
                    e_iso = e_dt.isoformat()
                except Exception:
                    e_iso = parse_dt(end_text)
            else:
                e_iso = parse_dt(end_text)
        start_s, end_s = s_iso, e_iso
    return start_s, end_s


def parse_list() -> list[dict[str, Any]]:
    print(f"Fetching list: {LIST_URL}")
    r = requests.get(LIST_URL, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    out: list[dict[str, Any]] = []

    # Cards are list items with href attribute pointing to /en/events/<id>
    cards = soup.select('li.MuiAccordion-root[href*="/en/events/"]')
    print(f"Found {len(cards)} cards")
    seen_ids: set[str] = set()
    for card in cards:
        href = card.get("href")
        if not href:
            continue
        abs_url = urljoin(BASE_URL, href)
        canon = canonical_event_url(abs_url)
        eid = event_id_from_url(canon)
        if not eid or eid in seen_ids:
            continue
        seen_ids.add(eid)

        # Title, subtitle/summary
        title_el = card.select_one("h2")
        name = title_el.get_text(strip=True) if title_el else None
        desc = None
        # Prefer expanded long description if present within the card
        long_region = card.select_one(".MuiAccordionDetails-root")
        if long_region:
            # Try to find the content container inside
            content = long_region.select_one("div.jss211") or long_region
            desc = to_markdown(str(content))
            # Trim common boilerplate
            desc = desc.strip()
        if not desc:
            # Fallback to short summary
            desc_el = card.select_one("div.jss54") or card.select_one("p")
            desc = desc_el.get_text(" ", strip=True) if desc_el else None

        # Time block
        time_block = card.select_one("div.jss55 div") or card.select_one("div.jss55")
        starts_at, ends_at = parse_time_range(time_block) if time_block else (None, None)

        # Location (usually last div within jss56)
        loc_block = card.select_one("div.jss56")
        location_name = None
        if loc_block:
            inners = [d.get_text(" ", strip=True) for d in loc_block.find_all("div")]
            if inners:
                location_name = inners[-1]

        # Poster image
        img_el = card.find("img")
        poster_src = normalize_image_src(img_el.get("src", "")) if img_el else None

        ev = ScrapedEvent(
            name=name or f"AMIV Event {eid}",
            description=desc or "",
            starts_at=starts_at,
            ends_at=ends_at,
            timezone=DEFAULT_TIMEZONE,
            location_name=location_name,
            link_url=canon,
            organizer_id=None,
            category=None,
            source=SOURCE,
            external_id=eid,
            is_public=True,
            tags=[],
        )

        # Download poster
        if poster_src:
            poster_dir = POSTERS_ROOT / eid
            fname = download_image(poster_src, poster_dir)
            if fname:
                ev.poster_url = f"/uploads/event/amiv/{eid}/{fname}"

        # If we still have a very short description, try fetching the detail page for a longer one
        if (not ev.description) or len(ev.description) < 40:
            try:
                time.sleep(REQUEST_DELAY_SEC)
                detail = requests.get(canon, timeout=20)
                if detail.status_code == 200:
                    dsoup = BeautifulSoup(detail.text, "html.parser")
                    # Heuristic: find main content with paragraphs
                    main = dsoup.find("main") or dsoup.find("article") or dsoup.find("div", attrs={"role": "main"})
                    if not main:
                        # broader fallback
                        main = dsoup
                    # Remove nav/headers/footers
                    for tag in main.find_all(["nav", "header", "footer"]):
                        tag.decompose()
                    # Prefer blocks with multiple paragraphs
                    cand = None
                    paras = main.find_all("p")
                    if paras:
                        root = paras[0].find_parent("div") or main
                        cand = root
                    else:
                        cand = main
                    md = to_markdown(str(cand))
                    md = md.strip()
                    if len(md) > len(ev.description or ""):
                        ev.description = md
            except Exception:
                pass

        out.append(ev.to_event_dict())

    return out


def main() -> None:
    ensure_dir(OUTPUT_JSON.parent)
    ensure_dir(POSTERS_ROOT)
    events = parse_list()
    OUTPUT_JSON.write_text(json.dumps(events, indent=2, ensure_ascii=False))
    print(f"Wrote {len(events)} events to {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
