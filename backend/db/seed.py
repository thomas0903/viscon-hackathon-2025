from __future__ import annotations

"""Seed data from JSON files under db/seed_data.

Assumes migrations have already created the tables (we don't call create_all).
Imports events, users, friendships, attendance, and tags (if provided).
"""

from datetime import datetime, timezone, timedelta
import json
import os
from pathlib import Path
import shutil
import random

from sqlalchemy import select

from .base import SessionLocal
from .models import (
    Event,
    EventAttendance,
    EventTag,
    Friendship,
    FriendshipStatus,
    RSVPStatus,
    User,
    VisibilityMode,
)


def _seed_dir_candidates() -> list[Path]:
    """Return likely seed data directories, most-specific first.

    Supports both packaged seeds under /app/db/seed_data and bind-mounted seeds at
    /app/backend/db/seed_data (as used by docker-compose). Also considers repo-level
    paths when running locally.
    """
    here = Path(__file__).resolve()
    db_dir = here.parent  # .../db
    app_root = db_dir.parent  # /app
    cwd = Path.cwd()
    candidates = [
        app_root / "var" / "seed_data",              # scrapers output here in container (prefer freshest)
        cwd / "var" / "seed_data",                  # local scraper output
        db_dir / "seed_data",                        # packaged with the image (/app/db/seed_data)
        app_root / "backend" / "db" / "seed_data",   # legacy bind-mounted path (if present)
        cwd / "backend" / "db" / "seed_data",       # local dev
        cwd / "db" / "seed_data",                   # alternate local
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


def _pick_seed_dir() -> Path | None:
    for d in _seed_dir_candidates():
        try:
            if any(d.glob("*.json")):
                return d
        except Exception:
            continue
    # Fallback to packaged path even if empty
    try:
        return (Path(__file__).parent / "seed_data")
    except Exception:
        return None


def _parse_dt(val):
    if val in (None, "", 0):
        return None
    if isinstance(val, datetime):
        return val
    s = str(val)
    try:
        return datetime.fromisoformat(s)
    except Exception:
        pass
    import re as _re
    m = _re.match(r"^(\d{4})(\d{2})(\d{2})T?(\d{2})(\d{2})(\d{2})$", s)
    if m:
        y, mo, d, hh, mm, ss = map(int, m.groups())
        return datetime(y, mo, d, hh, mm, ss)
    return None


def _upsert_user(id: int | str, **fields) -> User:
    with SessionLocal() as session:
        sid = str(id)
        user = session.get(User, sid)
        if user is None:
            user = User(id=sid, **fields)
            session.add(user)
        else:
            for k, v in fields.items():
                setattr(user, k, v)
        session.commit()
        session.refresh(user)
        return user


def _upsert_event(id: int | str, **fields) -> Event:
    with SessionLocal() as session:
        sid = str(id)
        event = session.get(Event, sid)
        if event is None:
            event = Event(id=sid, **fields)
            session.add(event)
        else:
            for k, v in fields.items():
                setattr(event, k, v)
        session.commit()
        session.refresh(event)
        return event


def _upsert_event_by_source(source: str, external_id: str, **fields) -> Event:
    """Upsert an event by its (source, external_id) unique key.

    Fields may include any Event columns except id/source/external_id which are fixed.
    """
    with SessionLocal() as session:
        existing = session.execute(
            select(Event).where(Event.source == source, Event.external_id == external_id)
        ).scalar_one_or_none()
        if existing is None:
            # Generate a stable string ID from source/external_id within 64 chars
            generated_id = (f"{source}:{external_id}")[:64]
            event = Event(id=generated_id, source=source, external_id=external_id, **fields)
            session.add(event)
            session.commit()
            session.refresh(event)
            return event
        else:
            for k, v in fields.items():
                # Do not overwrite immutable keys
                if k in {"id", "source", "external_id"}:
                    continue
                setattr(existing, k, v)
            session.commit()
            session.refresh(existing)
            return existing


def _ensure_friendship(a: int | str, b: int | str, requester: int | str, status: FriendshipStatus, accepted: bool = False) -> Friendship:
    # Enforce ordering: user_id < friend_id
    a_s, b_s = str(a), str(b)
    user_id, friend_id = sorted([a_s, b_s])
    accepted_at = datetime.now(timezone.utc) if accepted else None
    with SessionLocal() as session:
        existing = session.execute(
            select(Friendship).where(
                Friendship.user_id == user_id, Friendship.friend_id == friend_id
            )
        ).scalar_one_or_none()
        if existing is not None:
            existing.status = status
            existing.requester_id = str(requester)
            if accepted:
                existing.accepted_at = accepted_at
            session.commit()
            session.refresh(existing)
            return existing

        fr = Friendship(
            id=f"{user_id}|{friend_id}",
            user_id=user_id,
            friend_id=friend_id,
            requester_id=str(requester),
            status=status,
            accepted_at=accepted_at,
        )
        session.add(fr)
        session.commit()
        session.refresh(fr)
        return fr


def _ensure_attendance(user_id: int | str, event_id: int | str, rsvp: RSVPStatus, visibility: VisibilityMode | None = None, checked_in: bool = False) -> EventAttendance:
    with SessionLocal() as session:
        uid, eid = str(user_id), str(event_id)
        existing = session.execute(
            select(EventAttendance).where(
                EventAttendance.user_id == uid, EventAttendance.event_id == eid
            )
        ).scalar_one_or_none()
        if existing is not None:
            existing.rsvp_status = rsvp
            existing.visibility_override = visibility
            session.commit()
            session.refresh(existing)
            return existing

        ea = EventAttendance(
            id=f"{uid}|{eid}",
            user_id=uid,
            event_id=eid,
            rsvp_status=rsvp,
            visibility_override=visibility,
            checked_in_at=(datetime.now(timezone.utc) if checked_in else None),
        )
        session.add(ea)
        session.commit()
        session.refresh(ea)
        return ea


def seed() -> None:
    """Insert data from JSON files."""
    _seed_events_from_json()
    _seed_users_from_json()
    _seed_friendships_from_json()
    _augment_default_user_friendships()
    _seed_attendance_from_json()
    print("Seed complete.")


def _seed_events_from_json() -> None:
    """Load events from JSON files across known seed directories and upsert them.

    Accepts either a top-level list of event dicts or an object with key 'events'.
    Adds tags if provided.
    Scans all candidate seed directories and de-duplicates by file path.
    """
    seed_dirs = _seed_dir_candidates()
    if not seed_dirs:
        return

    default_organizer = os.getenv("SEED_DEFAULT_ORGANIZER_ID")  # string user id if provided

    def add_tag(session, event_id: int, tag: str) -> None:
        exists = session.get(EventTag, {"event_id": event_id, "tag": tag})
        if not exists:
            session.add(EventTag(event_id=event_id, tag=tag))
            session.commit()

    # Only consume event JSONs here; user/friend/attendance are handled separately
    # Support both "events.*.json" and "*_events.json" naming schemes
    files_set: set[Path] = set()
    for base in seed_dirs:
        for pattern in ("events*.json", "*_events.json"):
            for p in base.glob(pattern):
                try:
                    files_set.add(p.resolve())
                except Exception:
                    files_set.add(p)
    json_files = sorted(files_set)
    if not json_files:
        return
    for jf in json_files:
        try:
            payload = json.loads(jf.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"Failed to read seed JSON {jf}: {e}")
            continue

        if isinstance(payload, dict) and "events" in payload and isinstance(payload["events"], list):
            items = payload["events"]
        elif isinstance(payload, list):
            items = payload
        else:
            print(f"Seed JSON {jf} has unexpected structure; skipping")
            continue

        for raw in items:
            if not isinstance(raw, dict):
                continue
            source = raw.get("source") or "external"
            external_id = raw.get("external_id") or raw.get("id") or None
            if not external_id:
                print(f"Skipping event without external_id in {jf}")
                continue

            # Copy recognized fields; skip malformed rows without a name
            org = raw.get("organizer_id") or default_organizer
            if org is not None:
                org = str(org)
                # Ensure organizer exists; otherwise clear to satisfy FK
                try:
                    with SessionLocal() as scheck:
                        if scheck.get(User, org) is None:
                            org = None
                except Exception:
                    org = None
            def _source_key(s: str) -> str:
                s_l = str(s).lower()
                if "vis" in s_l:
                    return "vis"
                if "amiv" in s_l:
                    return "amiv"
                # fallback: take first DNS label or sanitize
                return s_l.split(".")[0] or s_l

            def _ensure_poster_file(src: str, ext_id: str, json_file: Path) -> str | None:
                """Copy a packaged seed image to var/uploads and return local URL.

                Looks under <json_dir>/images/<source_key>/<ext_id>/poster.*
                """
                key = _source_key(src)
                base_dir = json_file.parent
                seed_images = base_dir / "images" / key / str(ext_id)
                if not seed_images.exists():
                    return None
                candidates = [
                    seed_images / "poster.jpg",
                    seed_images / "poster.jpeg",
                    seed_images / "poster.png",
                    seed_images / "poster.webp",
                    seed_images / "poster.svg",
                ]
                chosen: Path | None = next((p for p in candidates if p.exists()), None)
                if chosen is None:
                    try:
                        for p in sorted(seed_images.iterdir()):
                            if p.is_file():
                                chosen = p
                                break
                    except Exception:
                        chosen = None
                if chosen is None:
                    return None

                uploads_root = Path("var") / "uploads" / "event" / key / str(ext_id)
                try:
                    uploads_root.mkdir(parents=True, exist_ok=True)
                except Exception:
                    return None
                dest = uploads_root / chosen.name
                try:
                    shutil.copy2(chosen, dest)
                except Exception:
                    return None
                return f"/uploads/event/{key}/{ext_id}/{dest.name}"

            # Build fields
            fields = {
                "name": raw.get("name"),
                "starts_at": _parse_dt(raw.get("starts_at")),
                "ends_at": _parse_dt(raw.get("ends_at")),
                "timezone": raw.get("timezone"),
                "location_name": raw.get("location_name"),
                "lat": raw.get("lat"),
                "lng": raw.get("lng"),
                "description": raw.get("description"),
                "link_url": raw.get("link_url"),
                "poster_url": raw.get("poster_url"),
                "organizer_id": org,
                "category": raw.get("category"),
                "is_public": bool(raw.get("is_public", True)),
            }

            if not fields["name"]:
                # Malformed/non-event entries; ignore
                continue

            # Ensure poster file is available locally and normalize URL if we have a seed image
            try:
                local_url = _ensure_poster_file(str(source), str(external_id), jf)
                if local_url:
                    fields["poster_url"] = local_url
            except Exception:
                pass

            ev = _upsert_event_by_source(str(source), str(external_id), **fields)

            # Tags
            tags = raw.get("tags") or []
            if isinstance(tags, list) and tags:
                with SessionLocal() as session:
                    for t in tags:
                        if not isinstance(t, str) or not t.strip():
                            continue
                        add_tag(session, ev.id, t.strip())


def _seed_users_from_json() -> None:
    seed_dirs = _seed_dir_candidates()
    if not seed_dirs:
        return
    files: set[Path] = set()
    for base in seed_dirs:
        for p in base.glob("users*.json"):
            try:
                files.add(p.resolve())
            except Exception:
                files.add(p)
    json_files = sorted(files)
    if not json_files:
        return
    for jf in json_files:
        try:
            items = json.loads(jf.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"Failed to read users JSON {jf}: {e}")
            continue
        if not isinstance(items, list):
            continue
        for raw in items:
            if not isinstance(raw, dict):
                continue
            sid = str(raw.get("id") or raw.get("username") or "").strip()
            if not sid:
                continue
            fields = {
                "first_name": raw.get("first_name"),
                "last_name": raw.get("last_name"),
                "username": raw.get("username") or sid,
                "email": raw.get("email"),
                "is_admin": bool(raw.get("is_admin", False)),
                "is_association": bool(raw.get("is_association", False)),
                "profile_picture_url": raw.get("profile_picture_url"),
                "visibility_mode": raw.get("visibility_mode") or VisibilityMode.all,
            }
            _upsert_user(sid, **fields)


def _seed_friendships_from_json() -> None:
    seed_dirs = _seed_dir_candidates()
    if not seed_dirs:
        return
    files: set[Path] = set()
    for base in seed_dirs:
        for p in base.glob("friendships*.json"):
            try:
                files.add(p.resolve())
            except Exception:
                files.add(p)
    json_files = sorted(files)
    if not json_files:
        return
    for jf in json_files:
        try:
            items = json.loads(jf.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"Failed to read friendships JSON {jf}: {e}")
            continue
        if not isinstance(items, list):
            continue
        with SessionLocal() as session:
            for raw in items:
                if not isinstance(raw, dict):
                    continue
                uid = str(raw.get("user_id") or "").strip()
                fid = str(raw.get("friend_id") or "").strip()
                if not uid or not fid:
                    continue
                a, b = (uid, fid) if uid < fid else (fid, uid)
                rid = str(raw.get("requester_id") or uid)
                fid_pk = raw.get("id") or f"{a}|{b}"
                existing = session.get(Friendship, str(fid_pk))
                if existing is None:
                    fr = Friendship(
                        id=str(fid_pk),
                        user_id=a,
                        friend_id=b,
                        requester_id=rid,
                        status=raw.get("status") or FriendshipStatus.accepted,
                        accepted_at=_parse_dt(raw.get("accepted_at")),
                    )
                    session.add(fr)
                else:
                    existing.status = raw.get("status") or existing.status
                    existing.requester_id = rid
                    if raw.get("accepted_at"):
                        existing.accepted_at = _parse_dt(raw.get("accepted_at"))
                session.commit()


def _seed_attendance_from_json() -> None:
    seed_dirs = _seed_dir_candidates()
    if not seed_dirs:
        return
    files: set[Path] = set()
    for base in seed_dirs:
        for p in base.glob("attendance*.json"):
            try:
                files.add(p.resolve())
            except Exception:
                files.add(p)
    json_files = sorted(files)
    if not json_files:
        return
    for jf in json_files:
        try:
            items = json.loads(jf.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"Failed to read attendance JSON {jf}: {e}")
            continue
        if not isinstance(items, list):
            continue
        with SessionLocal() as session:
            for raw in items:
                if not isinstance(raw, dict):
                    continue
                uid = str(raw.get("user_id") or "").strip()
                eid = str(raw.get("event_id") or "").strip()
                if not uid or not eid:
                    continue
                aid = raw.get("id") or f"{uid}|{eid}"
                existing = session.get(EventAttendance, str(aid))
                if existing is None:
                    ea = EventAttendance(
                        id=str(aid),
                        user_id=uid,
                        event_id=eid,
                        rsvp_status=raw.get("rsvp_status") or RSVPStatus.going,
                        visibility_override=raw.get("visibility_override"),
                        checked_in_at=_parse_dt(raw.get("checked_in_at")),
                    )
                    session.add(ea)
                else:
                    existing.rsvp_status = raw.get("rsvp_status") or existing.rsvp_status
                    existing.visibility_override = raw.get("visibility_override") or existing.visibility_override
                    if raw.get("checked_in_at"):
                        existing.checked_in_at = _parse_dt(raw.get("checked_in_at"))
                session.commit()


def _augment_default_user_friendships() -> None:
    """Ensure the default user has a realistic set of friends consistent with clustering.

    Strategy:
    - Pick a high-degree anchor user (proxy for a community hub)
    - Connect the default user to the anchor and a sample of the anchor's neighbors
    - Choose requester probabilistically by degree (mirrors generator)
    - Accept immediately and set accepted_at to a recent random time
    """
    # Configurable knobs
    default_user_id = os.getenv("SEED_DEFAULT_USER_ID") or os.getenv("DEFAULT_USER_ID") or "dev-user"
    try:
        target_friends = int(os.getenv("SEED_DEFAULT_USER_FRIENDS", "12"))
    except Exception:
        target_friends = 12

    if target_friends <= 0:
        return

    # Ensure default user exists
    _upsert_user(
        default_user_id,
        first_name=(os.getenv("SEED_DEFAULT_USER_FIRST", "Dev")),
        last_name=(os.getenv("SEED_DEFAULT_USER_LAST", "User")),
        username=default_user_id,
        email=None,
        is_admin=False,
        is_association=False,
        profile_picture_url=None,
        visibility_mode=VisibilityMode.all,
    )

    with SessionLocal() as session:
        # Build adjacency and degree maps from existing friendships
        friendships = session.execute(select(Friendship)).scalars().all()
        adjacency: dict[str, set[str]] = {}
        for fr in friendships:
            adjacency.setdefault(fr.user_id, set()).add(fr.friend_id)
            adjacency.setdefault(fr.friend_id, set()).add(fr.user_id)

        # If default user already has enough friends, nothing to do
        dev_neighbors = set(adjacency.get(default_user_id, set()))
        if len(dev_neighbors) >= target_friends:
            return

        # Compute degrees (fallback 0 for isolates)
        degrees: dict[str, int] = {u: len(vs) for u, vs in adjacency.items()}

        # Choose an anchor: highest-degree non-default user; fallback to any user
        anchor_id: str | None = None
        for uid, _deg in sorted(degrees.items(), key=lambda kv: kv[1], reverse=True):
            if uid != default_user_id:
                anchor_id = uid
                break
        if anchor_id is None:
            # Fallback if no friendships exist yet: pick any user
            any_user = session.execute(select(User).where(User.id != default_user_id)).scalars().first()
            if not any_user:
                return
            anchor_id = any_user.id

        # Candidate pool: anchor's neighbors (same community proxy)
        anchor_neighbors = list(adjacency.get(anchor_id, set()))
        random.shuffle(anchor_neighbors)

        # Ensure friendship with anchor itself first
        created_any = False
        if anchor_id not in dev_neighbors and anchor_id != default_user_id:
            # Degrees for requester probability
            deg_dev = len(dev_neighbors)
            deg_anchor = degrees.get(anchor_id, 0)
            p_dev_requests = (deg_dev / (deg_dev + deg_anchor)) if (deg_dev + deg_anchor) > 0 else 0.0
            requester = default_user_id if random.random() < p_dev_requests else anchor_id
            # Use helper to enforce ordering and acceptance
            fr = _ensure_friendship(default_user_id, anchor_id, requester, FriendshipStatus.accepted, accepted=True)
            # Manually backdate accepted_at a bit to diversify timestamps
            try:
                back = timedelta(days=random.randint(1, 120), seconds=random.randint(0, 24 * 3600 - 1))
                fr.accepted_at = datetime.now(timezone.utc) - back
                session.add(fr)
                session.commit()
            except Exception:
                pass
            dev_neighbors.add(anchor_id)
            degrees[default_user_id] = degrees.get(default_user_id, 0) + 1
            created_any = True

        # Fill remaining slots from anchor's neighborhood
        remaining = max(0, target_friends - len(dev_neighbors))
        if remaining <= 0:
            return

        # Exclude existing friends and self
        candidates = [u for u in anchor_neighbors if u != default_user_id and u not in dev_neighbors]
        if not candidates:
            # Fallback: sample from any users other than default
            candidates = [u.id for u in session.execute(select(User.id).where(User.id != default_user_id)).all()]
            candidates = [str(x[0]) for x in candidates if str(x[0]) not in dev_neighbors]

        random.shuffle(candidates)
        selected = candidates[:remaining]

        deg_dev = degrees.get(default_user_id, 0)
        for vid in selected:
            if vid == default_user_id:
                continue
            if vid in dev_neighbors:
                continue
            deg_v = degrees.get(vid, 0)
            p_dev_requests = (deg_dev / (deg_dev + deg_v)) if (deg_dev + deg_v) > 0 else 0.0
            requester = default_user_id if random.random() < p_dev_requests else vid
            fr = _ensure_friendship(default_user_id, vid, requester, FriendshipStatus.accepted, accepted=True)
            try:
                back = timedelta(days=random.randint(1, 365), seconds=random.randint(0, 24 * 3600 - 1))
                fr.accepted_at = datetime.now(timezone.utc) - back
                session.add(fr)
                session.commit()
            except Exception:
                pass
            dev_neighbors.add(vid)
            deg_dev += 1
            degrees[default_user_id] = deg_dev

def smoke_check() -> None:
    """Print a quick summary and example query to verify the seed."""
    with SessionLocal() as session:
        users = session.execute(select(User)).scalars().all()
        events = session.execute(select(Event)).scalars().all()
        attendance = session.execute(select(EventAttendance)).scalars().all()
        friendships = session.execute(select(Friendship)).scalars().all()
        print(f"Users: {len(users)} | Events: {len(events)} | Attendance: {len(attendance)} | Friendships: {len(friendships)}")


if __name__ == "__main__":
    seed()
    smoke_check()
