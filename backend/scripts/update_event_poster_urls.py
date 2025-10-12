from __future__ import annotations

"""
Update poster_url for existing events JSON files by visiting each event's link_url
and extracting the best image URL from the page, without re-scraping other fields.

Usage examples (run from repo root or backend/):
  python backend/scripts/update_event_poster_urls.py
  python backend/scripts/update_event_poster_urls.py backend/scripts/backend/db/seed_data/vis_events.json
  python backend/scripts/update_event_poster_urls.py backend/db/seed_data/events.amiv.json backend/db/seed_data/events.vis.json

Behavior:
- If file paths are provided as CLI args, only those files are updated.
- Otherwise, scans common seed directories for events*.json and *_events.json files.
- Supports both top-level list and {"events": [...]} structures.
- Only poster_url is updated; other fields remain unchanged.
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urljoin, urlparse, parse_qs, unquote, urlunparse

import requests
from bs4 import BeautifulSoup


REQUEST_DELAY_SEC = float(os.getenv("UPDATE_POSTER_DELAY_SEC", "0.1"))
HTTP_TIMEOUT_SEC = float(os.getenv("UPDATE_POSTER_TIMEOUT_SEC", "20"))
DEFAULT_UA = os.getenv(
    "UPDATE_POSTER_UA",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
)


def _seed_dirs() -> list[Path]:
    here = Path(__file__).resolve()
    script_dir = here.parent  # .../backend/scripts
    backend_dir = script_dir.parent  # .../backend
    repo_root = backend_dir.parent  # .../
    # Build robust absolute candidates regardless of CWD
    candidates = [
        repo_root / "backend" / "db" / "seed_data",
        backend_dir / "db" / "seed_data",
        Path.cwd() / "backend" / "db" / "seed_data",
        Path.cwd() / "db" / "seed_data",
    ]
    # Optional override via env: UPDATE_POSTER_SEED_DIRS=path1:path2
    extra = os.getenv("UPDATE_POSTER_SEED_DIRS", "").split(os.pathsep)
    for raw in extra:
        raw = raw.strip()
        if raw:
            candidates.append(Path(raw))
    out: list[Path] = []
    seen: set[str] = set()
    for p in candidates:
        try:
            rp = str(p.resolve())
            if Path(rp).exists() and rp not in seen:
                out.append(Path(rp))
                seen.add(rp)
        except Exception:
            continue
    return out


def _find_event_files_from_dirs() -> list[Path]:
    files: list[Path] = []
    for base in _seed_dirs():
        for pat in ("events*.json", "*_events.json"):
            for jf in base.glob(pat):
                try:
                    if jf.is_file():
                        files.append(jf.resolve())
                except Exception:
                    continue
    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[Path] = []
    for p in files:
        s = str(p)
        if s in seen:
            continue
        seen.add(s)
        unique.append(p)
    return unique


def _load_events_payload(path: Path) -> tuple[list[dict[str, Any]], bool]:
    """Return (events_list, is_wrapped) where is_wrapped indicates {"events": [...]} wrapper.
    If the file isn't recognized as events JSON, returns ([], False).
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return [], False
    if isinstance(raw, dict) and isinstance(raw.get("events"), list):
        events = [ev for ev in raw.get("events", []) if isinstance(ev, dict)]
        return events, True
    if isinstance(raw, list):
        events = [ev for ev in raw if isinstance(ev, dict)]
        return events, False
    return [], False


def _save_events_payload(path: Path, events: list[dict[str, Any]], is_wrapped: bool) -> None:
    if is_wrapped:
        payload: dict[str, Any] = {"events": events}
    else:
        payload = events
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))


def _normalize_amiv_image(src: str) -> str:
    """AMIV often uses Next.js image proxy '/_next/image?url=<real>&w=...'; extract real URL."""
    try:
        u = urlparse(src)
        if u.path.startswith("/_next/image"):
            qs = parse_qs(u.query)
            real = qs.get("url", [""])[0]
            if real:
                real = unquote(real)
                if real.startswith("/"):
                    return urljoin("https://amiv.ethz.ch", real)
                return real
    except Exception:
        pass
    if src.startswith("/"):
        return urljoin("https://amiv.ethz.ch", src)
    return src


def _extract_poster_url(page_html: str, page_url: str) -> Optional[str]:
    soup = BeautifulSoup(page_html, "html.parser")

    # Try JSON-LD Event 'image'
    try:
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
                img = ev.get("image")
                if isinstance(img, list) and img:
                    return urljoin(page_url, img[0])
                if isinstance(img, str) and img.strip():
                    return urljoin(page_url, img.strip())
    except Exception:
        pass

    # Meta tags
    for name in ("og:image", "twitter:image"):  # prioritize og
        try:
            el = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
            if el and el.get("content"):
                return urljoin(page_url, el["content"].strip())
        except Exception:
            continue

    # Prefer best candidate from <img> including srcset/data-src
    def _best_img_src(img_el: Any) -> Optional[str]:
        if not img_el:
            return None
        # direct src
        src = (img_el.get("src") or img_el.get("data-src") or "").strip()
        if src:
            return urljoin(page_url, src)
        # srcset
        srcset = (img_el.get("srcset") or img_el.get("data-srcset") or "").strip()
        if srcset:
            try:
                # pick the last candidate (often largest) or the one with highest width descriptor
                candidates: list[tuple[int, str]] = []
                for part in srcset.split(","):
                    p = part.strip()
                    if not p:
                        continue
                    tokens = p.split()
                    url = tokens[0]
                    w = 0
                    if len(tokens) > 1 and tokens[1].endswith("w"):
                        try:
                            w = int(tokens[1][:-1])
                        except Exception:
                            w = 0
                    candidates.append((w, url))
                if candidates:
                    candidates.sort(key=lambda t: t[0])
                    return urljoin(page_url, candidates[-1][1])
            except Exception:
                pass
        return None

    # Fallback: first <img> in main/article/body
    try:
        scope = soup.find("main") or soup.find("article") or soup
        img = scope.find("img") if scope else None
        best = _best_img_src(img)
        if best:
            return best
    except Exception:
        pass

    return None


# -------- VIS listing fallback (prefer card image over generic OG on detail) --------
def _vis_list_poster_map(session: requests.Session) -> dict[str, str]:
    """Return mapping external_id -> absolute poster URL from VIS listing page."""
    LIST_URL = "https://vis.ethz.ch/en/events/"
    try:
        r = session.get(LIST_URL, timeout=HTTP_TIMEOUT_SEC)
        if r.status_code != 200:
            return {}
    except Exception:
        return {}
    soup = BeautifulSoup(r.text, "html.parser")
    cards = soup.select("div.event-column div.card, div.card.full-height")
    out: dict[str, str] = {}
    for card in cards:
        a = card.find("a", href=True)
        if not a:
            continue
        abs_url = urljoin(LIST_URL, a["href"].strip())
        # Expect /en/events/<id>/
        path = urlparse(abs_url).path.rstrip("/")
        parts = path.split("/")
        if len(parts) < 4 or parts[-2] != "events" or not parts[-1].isdigit():
            continue
        eid = parts[-1]
        img = card.select_one("img.card-img-top") or card.find("img")
        poster_src: Optional[str] = None
        if img:
            # prefer src, then data-src, then best from srcset
            poster_src = (img.get("src") or img.get("data-src") or "").strip()
            if not poster_src:
                srcset = (img.get("srcset") or img.get("data-srcset") or "").strip()
                if srcset:
                    try:
                        candidates: list[tuple[int, str]] = []
                        for part in srcset.split(","):
                            p = part.strip()
                            if not p:
                                continue
                            tokens = p.split()
                            url = tokens[0]
                            w = 0
                            if len(tokens) > 1 and tokens[1].endswith("w"):
                                try:
                                    w = int(tokens[1][:-1])
                                except Exception:
                                    w = 0
                            candidates.append((w, url))
                        if candidates:
                            candidates.sort(key=lambda t: t[0])
                            poster_src = candidates[-1][1]
                    except Exception:
                        poster_src = None
        if poster_src:
            abs_poster = urljoin(LIST_URL, poster_src)
            out[eid] = _normalize_vis_image(abs_poster)
    return out


# -------- AMIV listing fallback (prefer card image) --------
def _amiv_list_poster_map(session: requests.Session) -> dict[str, str]:
    """Return mapping external_id -> absolute poster URL from AMIV listing page."""
    LIST_URL = "https://amiv.ethz.ch/en/events"
    try:
        r = session.get(LIST_URL, timeout=HTTP_TIMEOUT_SEC)
        if r.status_code != 200:
            return {}
    except Exception:
        return {}
    soup = BeautifulSoup(r.text, "html.parser")
    out: dict[str, str] = {}
    # Cards are list items with href to /en/events/<id>
    cards = soup.select('li.MuiAccordion-root[href*="/en/events/"]')
    for card in cards:
        href = card.get("href")
        if not href:
            continue
        abs_url = urljoin(LIST_URL, href)
        u = urlparse(abs_url)
        # Extract <id>
        parts = u.path.rstrip("/").split("/")
        if len(parts) < 4 or parts[-2] != "events":
            continue
        eid = parts[-1]
        img_el = card.find("img")
        if not img_el or not img_el.get("src"):
            continue
        src = img_el.get("src", "").strip()
        # Normalize AMIV proxy/src
        poster = _normalize_amiv_image(src)
        out[eid] = poster
    return out


def _update_file(path: Path) -> tuple[int, int]:
    events, is_wrapped = _load_events_payload(path)
    if not events:
        return 0, 0

    updated = 0
    tried = 0

    session = requests.Session()
    session.headers["User-Agent"] = DEFAULT_UA

    # Preload listing maps once per file to avoid per-detail generic OG fallbacks
    vis_map: dict[str, str] = {}
    amiv_map: dict[str, str] = {}
    # Detect source by scanning events
    has_vis = any("vis.ethz.ch" in str(ev.get("link_url") or "") for ev in events)
    has_amiv = any("amiv.ethz.ch" in str(ev.get("link_url") or "") for ev in events)
    if has_vis:
        vis_map = _vis_list_poster_map(session)
    if has_amiv:
        amiv_map = _amiv_list_poster_map(session)

    for ev in events:
        link = str(ev.get("link_url") or "").strip()
        if not link:
            continue
        tried += 1
        poster: Optional[str] = None
        # Try listing maps first to avoid generic site-wide OG images on detail pages
        if "vis.ethz.ch" in link:
            # id is the last path segment
            parts = urlparse(link).path.rstrip("/").split("/")
            if len(parts) >= 4 and parts[-2] == "events" and parts[-1].isdigit():
                poster = vis_map.get(parts[-1])
        elif "amiv.ethz.ch" in link:
            parts = urlparse(link).path.rstrip("/").split("/")
            if len(parts) >= 4 and parts[-2] == "events":
                poster = amiv_map.get(parts[-1])
        # If no listing poster found, fetch detail page as fallback
        if not poster:
            time.sleep(REQUEST_DELAY_SEC)
            try:
                r = session.get(link, timeout=HTTP_TIMEOUT_SEC)
                if r.status_code == 200:
                    poster = _extract_poster_url(r.text, link)
            except Exception:
                poster = None
        if not poster:
            continue
        if "amiv.ethz.ch" in link:
            poster = _normalize_amiv_image(poster)
        elif "vis.ethz.ch" in link:
            poster = _normalize_vis_image(poster)
        if str(ev.get("poster_url") or "").strip() != poster:
            ev["poster_url"] = poster
            updated += 1

    if updated > 0:
        _save_events_payload(path, events, is_wrapped)

    return tried, updated


def _normalize_vis_image(src: str) -> str:
    """Normalize VIS image URLs to a stable, cacheable form.

    - Rewrite MinIO pre-signed URLs to CDN and drop AWS query params
    - Make relative paths absolute against vis.ethz.ch
    """
    if not src:
        return src
    try:
        u = urlparse(src)
        # If relative path, attach base
        if not u.scheme:
            return urljoin("https://vis.ethz.ch", src)
        # Rewrite MinIO signed URLs to CDN (strip query)
        host = (u.netloc or "").lower()
        if host.endswith("minio.vis.ethz.ch"):
            u = u._replace(netloc="cdn.vis.ethz.ch", query="")
            return urlunparse(u)
        # Otherwise, if query contains AWS signature params, strip them
        if any(k in (u.query or "").lower() for k in ("x-amz-algorithm", "x-amz-credential", "x-amz-date", "x-amz-expires", "x-amz-signature")):
            u = u._replace(query="")
            return urlunparse(u)
        return src
    except Exception:
        return src


def main(argv: list[str]) -> None:
    # Resolve target files
    if len(argv) > 1:
        targets: list[Path] = []
        for a in argv[1:]:
            p = Path(a)
            if p.exists() and p.is_file():
                targets.append(p.resolve())
        if not targets:
            print("No valid files provided.")
            return
    else:
        targets = _find_event_files_from_dirs()
        # Filter to likely AMIV/VIS event lists
        targets = [p for p in targets if "events" in p.name and p.suffix == ".json"]

    total_tried = 0
    total_updated = 0
    for tf in targets:
        tried, updated = _update_file(tf)
        total_tried += tried
        total_updated += updated
        print(f"{tf}: checked={tried}, updated={updated}")

    print(f"Done. Total checked={total_tried}, total updated={total_updated} across {len(targets)} file(s).")


if __name__ == "__main__":
    main(sys.argv)


