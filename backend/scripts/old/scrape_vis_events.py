from __future__ import annotations

"""
Scrape upcoming events from https://vis.ethz.ch/en/events/ and write:
- JSON to backend/db/seed_data/events.vis.json
- Poster URLs link to the original site (no image download)

Usage (host):
  python backend/scripts/scrape_vis_events.py

Install deps once:
  pip install -r backend/scripts/requirements-scraper.txt

Notes
- Respects a polite delay of 0.1s between requests.
- Stores description as Markdown (uses markdownify if available, falls back to plain text).
- Dates are stored as ISO 8601 strings; timezone set to Europe/Zurich when missing.
"""

import json
import os
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
import os
from typing import Any, Optional
from urllib.parse import urljoin, urlparse, urlunparse, parse_qs

import requests
from bs4 import BeautifulSoup

try:
    from markdownify import markdownify as html_to_md  # type: ignore
except Exception:  # pragma: no cover
    html_to_md = None  # fall back later

try:
    from dateutil import parser as dateparser
    from dateutil import tz as datetz
except Exception as e:  # pragma: no cover
    raise RuntimeError("python-dateutil is required for this script") from e


BASE_URL = "https://vis.ethz.ch"
LIST_URL = "https://vis.ethz.ch/en/events/"

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

# Always store images under container/application upload root
UPLOAD_ROOT = Path("var/uploads")
POSTERS_ROOT = UPLOAD_ROOT / "event" / "vis"

OUTPUT_JSON = SEED_DIR / "events.vis.json"
REQUEST_DELAY_SEC = float(os.getenv("SCRAPER_DELAY_SEC", "0.1"))
DEFAULT_TIMEZONE = "Europe/Zurich"
SOURCE = "vis.ethz.ch"


def slug_from_url(url: str) -> str:
    path = urlparse(url).path.rstrip("/")
    slug = path.split("/")[-1] or "event"
    # normalize
    slug = re.sub(r"[^a-zA-Z0-9-_]", "-", slug).strip("-").lower()
    return slug or "event"


def to_markdown(html: str) -> str:
    if not html:
        return ""
    if html_to_md is not None:
        return html_to_md(html, heading_style="ATX")
    # naive fallback: strip tags
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text("\n").strip()


def pick_meta(soup: BeautifulSoup, *names: str) -> Optional[str]:
    for n in names:
        el = soup.find("meta", attrs={"property": n}) or soup.find("meta", attrs={"name": n})
        if el and el.get("content"):
            return el["content"].strip()
    return None


def parse_jsonld_event(soup: BeautifulSoup) -> dict[str, Any] | None:
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.text)
        except Exception:
            continue

        def walk(obj: Any):
            if isinstance(obj, dict):
                if obj.get("@type") == "Event":
                    return obj
                for v in obj.values():
                    res = walk(v)
                    if res:
                        return res
            elif isinstance(obj, list):
                for v in obj:
                    res = walk(v)
                    if res:
                        return res
            return None

        ev = walk(data)
        if ev:
            return ev  # type: ignore
    return None


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def download_image(url: str, dest_dir: Path) -> Optional[str]:
    if not url:
        return None
    ensure_dir(dest_dir)
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
    }.get(ctype)
    if not ext:
        # fallback from URL
        path = urlparse(url).path
        m = re.search(r"\.(jpg|jpeg|png|webp|gif)$", path, re.IGNORECASE)
        ext = f".{m.group(1).lower()}" if m else ".jpg"
    filename = f"poster{ext}"
    (dest_dir / filename).write_bytes(resp.content)
    return filename


def parse_dt(val: Any) -> Optional[str]:
    if not val:
        return None
    try:
        # Prefer European day-first when ambiguous; map CET/CEST
        tzinfos = {"CET": datetz.gettz("Europe/Zurich"), "CEST": datetz.gettz("Europe/Zurich")}
        dt = dateparser.parse(str(val), dayfirst=True, tzinfos=tzinfos)
        if not dt:
            return None
        # Store naive ISO; timezone provided separately
        return dt.replace(tzinfo=None).isoformat()
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
        # Only fields matching backend Event should be saved (plus tags)
        d = asdict(self)
        return d


def canonical_event_url(url: str) -> str:
    """Return the event detail URL without fragments or non-detail suffixes."""
    u = urlparse(url)
    # strip fragment and query
    u = u._replace(fragment="", query="")
    # Normalize path to /en/events/<id>/
    parts = u.path.rstrip("/").split("/")
    # Expect .../en/events/<id>
    if len(parts) >= 4 and parts[-2] == "events" and parts[-1].isdigit():
        path = "/".join(parts[:4]) + "/"
        u = u._replace(path=path)
    return urlunparse(u)


def _find_calendar_times(soup: BeautifulSoup) -> tuple[Optional[str], Optional[str]]:
    """Parse Google Calendar link on the page to extract start/end in ISO strings.

    Looks for dates=YYYYMMDD[T]HHMMSS/YYYYMMDD[T]HHMMSS.
    Returns (starts_at, ends_at) as ISO strings (naive), or (None, None).
    """
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "calendar.google.com/calendar/render" not in href:
            continue
        try:
            u = urlparse(href)
            qs = parse_qs(u.query)
            dates = qs.get("dates", [])
            if not dates:
                # Some links may use fragment; fallback to whole string search
                m = re.search(r"dates=([0-9T]+)/([0-9T]+)", href)
                if not m:
                    continue
                raw = f"{m.group(1)}/{m.group(2)}"
            else:
                raw = dates[0]
            m = re.match(r"(\d{8}T?\d{6})/(\d{8}T?\d{6})", raw)
            if not m:
                continue
            s_raw, e_raw = m.groups()
            s_iso = parse_dt(s_raw)
            e_iso = parse_dt(e_raw)
            return s_iso, e_iso
        except Exception:
            continue
    return None, None


def _find_label_times(soup: BeautifulSoup) -> tuple[Optional[str], Optional[str]]:
    """Parse human-readable labels like:
    <b>Event start time 11.10.2025 08:30</b>
    <b>Event end time 11.10.2025 18:00</b>
    """
    s_iso: Optional[str] = None
    e_iso: Optional[str] = None
    for el in soup.find_all(["b", "strong"]):
        text = el.get_text(" ", strip=True)
        if not text:
            continue
        m = re.search(r"^\s*Event\s+start\s+time\s+(.+)$", text, re.IGNORECASE)
        if m and not s_iso:
            s_iso = parse_dt(m.group(1))
        m2 = re.search(r"^\s*Event\s+end\s+time\s+(.+)$", text, re.IGNORECASE)
        if m2 and not e_iso:
            e_iso = parse_dt(m2.group(1))
    return s_iso, e_iso


def _clean_description_html(main: BeautifulSoup) -> str:
    # Remove scripts, styles, noscript, and images
    for tag_name in ["script", "style", "noscript"]:
        for t in main.find_all(tag_name):
            t.decompose()
    for img in main.find_all("img"):
        img.decompose()
    # Remove the first h1 (title duplicate)
    h1 = main.find("h1")
    if h1:
        h1.decompose()
    # Remove obvious noise blocks by keywords
    patterns = [r"Add to calendar", r"Event start time", r"Event end time", r"All events"]
    for pat in patterns:
        for textnode in main.find_all(string=re.compile(pat, re.I)):
            # remove the closest block-level ancestor
            parent = textnode
            for _ in range(3):
                if hasattr(parent, "name") and parent.name in {"p", "div", "section", "strong", "li"}:
                    break
                parent = parent.parent or parent
            try:
                parent.decompose()
            except Exception:
                pass
    return str(main)


def event_id_from_url(url: str) -> Optional[str]:
    p = urlparse(url).path.rstrip("/")
    parts = p.split("/")
    if parts and parts[-1].isdigit():
        return parts[-1]
    if len(parts) >= 2 and parts[-2].isdigit():
        return parts[-2]
    return None


def extract_event_details(url: str, list_hints: dict[str, Any] | None = None) -> Optional[ScrapedEvent]:
    time.sleep(REQUEST_DELAY_SEC)
    r = requests.get(url, timeout=20)
    if r.status_code != 200:
        return None
    soup = BeautifulSoup(r.text, "html.parser")

    title = None
    if soup.find("h1"):
        title = soup.find("h1").get_text(strip=True)
    if not title:
        # fallback to og:title
        title = pick_meta(soup, "og:title")
    if not title:
        return None

    # Prefer JSON-LD Event for structured data if present
    ev_ld = parse_jsonld_event(soup)

    desc_md = None
    starts_at = None
    ends_at = None
    location_name = None
    poster_src = None
    category = None
    tags: list[str] = []

    if ev_ld:
        desc_html = ev_ld.get("description")
        desc_md = to_markdown(desc_html) if isinstance(desc_html, str) else None
        starts_at = parse_dt(ev_ld.get("startDate"))
        ends_at = parse_dt(ev_ld.get("endDate"))
        loc = ev_ld.get("location")
        if isinstance(loc, dict):
            location_name = loc.get("name") or loc.get("address") or None
        img = ev_ld.get("image")
        if isinstance(img, list) and img:
            poster_src = img[0]
        elif isinstance(img, str):
            poster_src = img
        category = ev_ld.get("eventStatus") or ev_ld.get("eventType")
        kw = ev_ld.get("keywords")
        if isinstance(kw, list):
            tags = [str(k) for k in kw]
        elif isinstance(kw, str):
            tags = [t.strip() for t in re.split(r",|;|\|", kw) if t.strip()]

    # Fallbacks from meta / page content
    if not desc_md:
        # Heuristic: prefer the left content column, else broader containers
        main = (
            soup.select_one("div.col-md-7 div.event-detail-column")
            or soup.find("article")
            or soup.find("main")
            or soup.find("div", class_=re.compile(r"content|main", re.I))
        )
        if main:
            cleaned_html = _clean_description_html(main)
            desc_md = to_markdown(cleaned_html)
        else:
            desc_md = None
    if not poster_src:
        poster_src = pick_meta(soup, "og:image", "twitter:image")
    # Fallback: first image inside an event image container, else any img in main content
    if not poster_src:
        container = soup.find("div", class_=re.compile(r"event-image", re.I))
        img_el = None
        if container:
            img_el = container.find("img")
        if not img_el:
            main_img_scope = soup.find("article") or soup.find("main") or soup
            img_el = main_img_scope.find("img") if main_img_scope else None
        if img_el and img_el.get("src"):
            poster_src = img_el["src"].strip()
    if not location_name:
        loc_el = soup.find(string=re.compile(r"Location|Where", re.I))
        if loc_el and loc_el.parent:
            location_name = loc_el.parent.get_text(strip=True)

    # Fallback: parse times from labels, then Google Calendar link if missing
    if not starts_at or not ends_at:
        s_iso_l, e_iso_l = _find_label_times(soup)
        starts_at = starts_at or s_iso_l
        ends_at = ends_at or e_iso_l
    if not starts_at or not ends_at:
        s_iso_c, e_iso_c = _find_calendar_times(soup)
        starts_at = starts_at or s_iso_c
        ends_at = ends_at or e_iso_c

    # Fallback: pull times/category/poster from listing hints
    canonical = canonical_event_url(url)
    slug = slug_from_url(canonical)
    eid = event_id_from_url(canonical)
    if list_hints and eid and (not starts_at or not ends_at):
        hint = list_hints.get(eid) or {}
        starts_at = starts_at or hint.get("starts_at")
        ends_at = ends_at or hint.get("ends_at")
        category = category or hint.get("category")
        if not poster_src:
            poster_src = hint.get("poster_src")

    # Category fallback from visible badge
    if not category:
        badge = soup.select_one("span.badge")
        if badge:
            txt = badge.get_text(strip=True)
            if txt:
                category = txt

    # Build event record
    ev = ScrapedEvent(
        name=title,
        description=desc_md or "",
        starts_at=starts_at,
        ends_at=ends_at,
        timezone=DEFAULT_TIMEZONE,
        location_name=location_name,
        link_url=canonical,
        organizer_id=None,
        category=category,
        source=SOURCE,
        external_id=slug,
        is_public=True,
        tags=tags,
    )

    # Download poster if available
    if poster_src:
        poster_abs = urljoin(canonical, poster_src)
        poster_dir = POSTERS_ROOT / slug
        filename = download_image(poster_abs, poster_dir)
        if filename:
            ev.poster_url = f"/uploads/event/vis/{slug}/{filename}"

    return ev


def parse_list_page(list_html: str) -> tuple[list[str], dict[str, dict[str, Any]]]:
    """Parse the listing page to collect event URLs and per-card hints.

    Returns: (urls, hints_by_id) where hints include starts_at, ends_at, category, poster_src
    """
    soup = BeautifulSoup(list_html, "html.parser")
    urls: list[str] = []
    hints: dict[str, dict[str, Any]] = {}

    # Each card is inside .event-column or .card.full-height
    cards = soup.select("div.event-column div.card, div.card.full-height")
    seen = set()
    for card in cards:
        a = card.find("a", href=True)
        if not a:
            continue
        abs_url = urljoin(BASE_URL, a["href"].strip())
        canon = canonical_event_url(abs_url)
        p = urlparse(canon).path.rstrip("/")
        if not re.match(r"^/en/events/\d+$", p):
            continue
        if canon in seen:
            continue
        seen.add(canon)
        urls.append(canon)

        eid = event_id_from_url(canon)
        if not eid:
            continue
        # times
        s_iso, e_iso = _find_label_times(card)
        # category
        badge = card.select_one("span.badge")
        cat = badge.get_text(strip=True) if badge else None
        # poster
        img = card.select_one("img.card-img-top") or card.find("img")
        poster_src = img.get("src").strip() if img and img.get("src") else None
        hints[eid] = {
            "starts_at": s_iso,
            "ends_at": e_iso,
            "category": cat,
            "poster_src": poster_src,
        }

    return urls, hints


def scrape() -> list[dict[str, Any]]:
    print(f"Fetching list: {LIST_URL}")
    r = requests.get(LIST_URL, timeout=20)
    r.raise_for_status()
    urls, hints = parse_list_page(r.text)
    print(f"Found {len(urls)} event URLs")

    out: list[dict[str, Any]] = []
    for i, url in enumerate(urls, start=1):
        print(f"[{i}/{len(urls)}] Scraping {url}")
        try:
            ev = extract_event_details(url, list_hints=hints)
            if not ev:
                print(f"  - skipped (parse error)")
                continue
            out.append(ev.to_event_dict())
        except Exception as e:
            print(f"  - error: {e}")
    return out


def main() -> None:
    ensure_dir(OUTPUT_JSON.parent)
    ensure_dir(POSTERS_ROOT)
    events = scrape()
    payload = events
    OUTPUT_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"Wrote {len(events)} events to {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
