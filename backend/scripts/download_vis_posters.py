from __future__ import annotations

"""
Download VIS event posters to var/uploads and link events to the local files.

Behavior:
- For VIS events (source == "vis.ethz.ch"):
  - If DB is available, update DB poster_url to local /uploads path after download.
  - Also update seed JSON files (e.g., backend/db/seed_data/vis_events.json) so poster_url points to the local /uploads path.
  - Images are stored under var/uploads/event/vis/<external_id>/poster.<ext>.

Run locally after seeding:
  PYTHONPATH=backend:. python backend/scripts/download_vis_posters.py
"""

import os
import json
import time
import re
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, urljoin

import requests
from bs4 import BeautifulSoup


REQUEST_TIMEOUT = float(os.getenv("VIS_DL_TIMEOUT", "20"))
REQUEST_DELAY = float(os.getenv("VIS_DL_DELAY", "0.1"))
UA = os.getenv(
    "VIS_DL_UA",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
)

UPLOAD_ROOT = Path("var/uploads")


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _pick_ext_from_content_type(ct: str) -> str:
    ct = (ct or "").split(";")[0].strip().lower()
    return {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }.get(ct, ".jpg")


def _best_img_src(img_el) -> Optional[str]:
    if not img_el:
        return None
    src = (img_el.get("src") or img_el.get("data-src") or "").strip()
    if src:
        return src
    srcset = (img_el.get("srcset") or img_el.get("data-srcset") or "").strip()
    if not srcset:
        return None
    try:
        candidates = []
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
            return candidates[-1][1]
    except Exception:
        return None
    return None


def _extract_signed_image(session: requests.Session, event_url: str) -> Optional[str]:
    try:
        r = session.get(event_url, timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            return None
    except Exception:
        return None
    soup = BeautifulSoup(r.text, "html.parser")
    # try first image on page
    img = soup.find("img")
    if img:
        src = _best_img_src(img) or img.get("src")
        if src:
            return urljoin(event_url, src.strip())
    # meta fallbacks
    for name in ("og:image", "twitter:image"):
        el = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
        if el and el.get("content"):
            return urljoin(event_url, el["content"].strip())
    return None


def _is_local(url: Optional[str]) -> bool:
    if not url:
        return False
    try:
        return str(url).startswith("/uploads/")
    except Exception:
        return False


def _file_exists_for_local(url: str) -> bool:
    # url looks like /uploads/event/<id>/<filename> -> map to var/uploads/event/<id>/<filename>
    if not url.startswith("/uploads/"):
        return False
    rel = url[len("/uploads/") :]
    disk_path = Path("var/uploads") / rel
    return disk_path.exists()


def _download_to(session: requests.Session, url: str, dest_dir: Path) -> Optional[str]:
    try:
        r = session.get(url, timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            return None
    except Exception:
        return None
    ext = _pick_ext_from_content_type(r.headers.get("Content-Type", ""))
    name = "poster" + ext
    _ensure_dir(dest_dir)
    (dest_dir / name).write_bytes(r.content)
    return name


def _seed_dirs() -> list[Path]:
    here = Path(__file__).resolve()
    script_dir = here.parent
    backend_dir = script_dir.parent
    repo_root = backend_dir.parent
    candidates = [
        backend_dir / "db" / "seed_data",
        repo_root / "backend" / "db" / "seed_data",
        Path.cwd() / "backend" / "db" / "seed_data",
        Path.cwd() / "db" / "seed_data",
    ]
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


def _load_events_payload(path: Path) -> tuple[list[dict], bool]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return [], False
    if isinstance(raw, dict) and isinstance(raw.get("events"), list):
        return [ev for ev in raw.get("events", []) if isinstance(ev, dict)], True
    if isinstance(raw, list):
        return [ev for ev in raw if isinstance(ev, dict)], False
    return [], False


def _save_events_payload(path: Path, events: list[dict], is_wrapped: bool) -> None:
    payload = {"events": events} if is_wrapped else events
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))


def _event_id_from_url(url: str) -> Optional[str]:
    p = urlparse(url).path.rstrip("/")
    parts = p.split("/")
    if parts and parts[-1].isdigit():
        return parts[-1]
    if len(parts) >= 2 and parts[-2].isdigit():
        return parts[-2]
    return None


def _process_seed_file(session: requests.Session, path: Path) -> tuple[int, int]:
    events, wrapped = _load_events_payload(path)
    if not events:
        return 0, 0
    tried = 0
    updated = 0
    changed = False
    for ev in events:
        link = str(ev.get("link_url") or "").strip()
        src = str(ev.get("source") or "")
        if not link and not src:
            continue
        if "vis.ethz.ch" not in link and src != "vis.ethz.ch":
            continue
        # Determine event id for folder naming
        eid = str(ev.get("external_id") or _event_id_from_url(link) or "").strip()
        if not eid:
            continue
        # Skip if local poster exists and json already points to it
        current = str(ev.get("poster_url") or "")
        if _is_local(current) and _file_exists_for_local(current):
            tried += 1
            continue
        # Fetch and download
        tried += 1
        img_url = _extract_signed_image(session, link or f"https://vis.ethz.ch/en/events/{eid}/")
        if not img_url:
            continue
        dest_dir = UPLOAD_ROOT / "event" / "vis" / eid
        filename = _download_to(session, img_url, dest_dir)
        if not filename:
            continue
        local_url = f"/uploads/event/vis/{eid}/{filename}"
        if current != local_url:
            ev["poster_url"] = local_url
            updated += 1
            changed = True
        # be polite
        time.sleep(REQUEST_DELAY)
    if changed:
        _save_events_payload(path, events, wrapped)
    return tried, updated


def run() -> None:
    _ensure_dir(UPLOAD_ROOT)
    session = requests.Session()
    session.headers["User-Agent"] = UA

    # Also update seed JSON files so future seeds are local-linking
    total_tried = 0
    total_updated = 0
    for base in _seed_dirs():
        for name in ("vis_events.json", "events.vis.json"):
            p = base / name
            if p.exists() and p.is_file():
                tried, updated = _process_seed_file(session, p)
                total_tried += tried
                total_updated += updated
    print(f"VIS posters: checked={total_tried}, updated={total_updated}")


if __name__ == "__main__":
    run()


