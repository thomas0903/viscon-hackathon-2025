from __future__ import annotations

"""
Generate a biased attendance JSON for an existing users/events dataset.

Defaults (overridable via env):
  ATT_USER_COUNT=100   # number of users to sample
  ATT_EVENT_COUNT=30   # number of events to sample
  ATT_TOPIC_COUNT=6    # number of latent topics
  FAKE_SEED=42         # random seed for reproducibility
  ATT_PREF_FRIEND_BETA=0.35  # influence strength from friends' preferences
  ATT_PREF_FRIEND_STEPS=2    # smoothing iterations across friendship graph

Usage (repo root or backend/):
  python backend/scripts/generate_biased_attendance.py

Output:
  backend/db/seed_data/attendance.gen.json (same format as generate_social_data.py)
"""

import json
import os
import random
from pathlib import Path
from typing import Iterable


# ------------- Paths & IO helpers -------------

def _seed_dir() -> Path:
    """Return the canonical seed data directory, creating it when necessary."""
    # Prefer app seed dir; fall back to repo-level db/seed_data if present
    app_seed = Path("backend/db/seed_data")
    repo_seed = Path("db/seed_data")
    if app_seed.exists():
        app_seed.mkdir(parents=True, exist_ok=True)
        return app_seed
    if repo_seed.exists():
        repo_seed.mkdir(parents=True, exist_ok=True)
        return repo_seed
    app_seed.mkdir(parents=True, exist_ok=True)
    return app_seed


def _events_dirs() -> list[Path]:
    """Candidate directories that may contain events*.json scraped files."""
    candidates = [
        Path("backend/db/seed_data"),
        Path("db/seed_data"),
        Path("backend/scripts/backend/db/seed_data"),
        Path(__file__).parent / "backend/db/seed_data",
    ]
    out: list[Path] = []
    seen: set[str] = set()
    for p in candidates:
        try:
            if p.exists():
                rp = str(p.resolve())
                if rp not in seen:
                    out.append(p.resolve())
                    seen.add(rp)
        except Exception:
            continue
    return out


def _iter_event_json_files() -> Iterable[Path]:
    """Yield event JSON files with specific names across known seed directories.

    Looks specifically for amiv_events.json and vis_events.json.
    """
    names = [
        "amiv_events.json",
        "vis_events.json",
    ]
    yielded: set[str] = set()
    for base in _events_dirs():
        for name in names:
            try:
                jf = (base / name).resolve()
                if jf.exists():
                    rp = str(jf)
                    if rp in yielded:
                        continue
                    yielded.add(rp)
                    yield jf
            except Exception:
                continue


def _load_users(max_users: int) -> list[dict]:
    """Load users from users.gen.json if present, otherwise synthesize placeholder users.

    Returns a list of user dicts with at least an "id" field.
    """
    locations: list[Path] = []
    for base in [Path("backend/db/seed_data"), Path("db/seed_data"), Path("backend/scripts/backend/db/seed_data")]:
        try:
            p = (base / "users.gen.json").resolve()
            if p.exists():
                locations.append(p)
        except Exception:
            pass

    users: list[dict] = []
    for loc in locations:
        try:
            data = json.loads(loc.read_text(encoding="utf-8"))
            if isinstance(data, list):
                users.extend(x for x in data if isinstance(x, dict) and x.get("id"))
        except Exception:
            continue

    if not users:
        # Synthesize placeholder users
        users = [{"id": f"user{i+1:03d}"} for i in range(max_users)]
    # Deduplicate by id while preserving order
    seen: set[str] = set()
    unique: list[dict] = []
    for u in users:
        uid = str(u.get("id"))
        if uid in seen:
            continue
        seen.add(uid)
        unique.append(u)

    # Sample up to max_users
    if len(unique) > max_users:
        unique = random.sample(unique, k=max_users)
    return unique


def _load_all_user_ids() -> list[str]:
    """Load all user ids from users.gen.json without sampling; may be empty.

    Deduplicates by id while preserving order.
    """
    locations: list[Path] = []
    for base in [Path("backend/db/seed_data"), Path("db/seed_data"), Path("backend/scripts/backend/db/seed_data")]:
        try:
            p = (base / "users.gen.json").resolve()
            if p.exists():
                locations.append(p)
        except Exception:
            pass

    ids: list[str] = []
    for loc in locations:
        try:
            data = json.loads(loc.read_text(encoding="utf-8"))
            if isinstance(data, list):
                for x in data:
                    if isinstance(x, dict) and x.get("id"):
                        ids.append(str(x.get("id")))
        except Exception:
            continue

    # Deduplicate while preserving order
    seen: set[str] = set()
    out: list[str] = []
    for uid in ids:
        if uid in seen:
            continue
        seen.add(uid)
        out.append(uid)
    return out


def _load_events_with_meta() -> list[dict]:
    """Load events from events*.json files and return [{id, category, name}] items.

    The event id format follows generate_social_data: f"{source}:{external_id}".
    """
    items: list[dict] = []
    for jf in _iter_event_json_files():
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
        except Exception:
            continue
        events = data.get("events") if isinstance(data, dict) else data
        if not isinstance(events, list):
            continue
        for ev in events:
            if not isinstance(ev, dict):
                continue
            src = str(ev.get("source") or "").strip()
            ext = str(ev.get("external_id") or "").strip()
            if not src or not ext:
                continue
            eid = f"{src}:{ext}"[:64]
            cat = ev.get("category")
            name = ev.get("name")
            items.append({
                "id": eid,
                "category": (str(cat) if cat is not None else "Misc").strip() or "Misc",
                "name": str(name) if name is not None else "",
            })
    # Dedup by id while keeping first metadata seen
    dedup: dict[str, dict] = {}
    for it in items:
        if it["id"] in dedup:
            continue
        dedup[it["id"]] = it
    return list(dedup.values())


def _load_friendships_adjacency() -> dict[str, set[str]]:
    """Load accepted friendships and return an undirected adjacency map.

    Scans likely seed directories for friendships.gen.json.
    """
    adj: dict[str, set[str]] = {}
    for base in _events_dirs():
        try:
            fpath = (base / "friendships.gen.json").resolve()
        except Exception:
            continue
        try:
            if not fpath.exists():
                continue
            data = json.loads(fpath.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                continue
        except Exception:
            continue
        for rec in data:
            if not isinstance(rec, dict):
                continue
            if str(rec.get("status") or "").lower() != "accepted":
                continue
            u = str(rec.get("user_id") or "").strip()
            v = str(rec.get("friend_id") or "").strip()
            if not u or not v or u == v:
                continue
            if u not in adj:
                adj[u] = set()
            if v not in adj:
                adj[v] = set()
            adj[u].add(v)
            adj[v].add(u)
    return adj


def _smooth_preferences_with_friends(
    user_ids: list[str],
    topics: list[str],
    user_topic_pref: dict[str, dict[str, float]],
    adjacency: dict[str, set[str]],
    *,
    beta: float = 0.35,
    steps: int = 2,
) -> dict[str, dict[str, float]]:
    """Diffuse preferences across the friendship graph to align clusters.

    Each step replaces a user's preference with a convex combination of their
    own and the weighted average of their neighbors' preferences.

    Neighbor weights are based on a combination of degree discount and
    neighborhood similarity (Jaccard) to emphasize closer ties.
    """
    if beta <= 0 or steps <= 0:
        return user_topic_pref

    # Precompute degrees
    degrees: dict[str, int] = {u: len(adjacency.get(u, set())) for u in user_ids}

    # Ensure all users exist in map
    for u in user_ids:
        if u not in user_topic_pref:
            user_topic_pref[u] = {t: 1.0 / max(1, len(topics)) for t in topics}

    for _ in range(steps):
        updated: dict[str, dict[str, float]] = {}
        for u in user_ids:
            base_pref = user_topic_pref[u]
            neighs = [v for v in adjacency.get(u, set()) if v in user_topic_pref]
            if not neighs:
                updated[u] = base_pref
                continue

            # Compute weighted neighbor average
            weights: list[tuple[str, float]] = []
            Nu = adjacency.get(u, set())
            for v in neighs:
                Nv = adjacency.get(v, set())
                # Jaccard similarity for closeness within cluster
                inter = len(Nu & Nv)
                union = len(Nu | Nv) or 1
                jacc = inter / union
                # Degree discount to downweight hubs
                deg_disc = 1.0 / (1.0 + (degrees.get(v, 0) ** 0.5))
                w = 1.0 + jacc
                w *= deg_disc
                weights.append((v, w))

            total_w = sum(w for _, w in weights) or 1.0
            # Aggregate neighbor distribution
            agg: dict[str, float] = {t: 0.0 for t in topics}
            for v, w in weights:
                pref_v = user_topic_pref[v]
                for t in topics:
                    agg[t] += w * float(pref_v.get(t, 0.0))
            for t in topics:
                agg[t] /= total_w

            # Blend with own preference and normalize
            blended = {t: (1.0 - beta) * float(base_pref.get(t, 0.0)) + beta * agg[t] for t in topics}
            # Normalize vector
            s = sum(blended.values()) or 1.0
            updated[u] = {t: blended[t] / s for t in topics}
        user_topic_pref = updated
    return user_topic_pref


# ------------- Stochastic helpers (pure stdlib) -------------

def _dirichlet(alphas: Iterable[float]) -> list[float]:
    """Sample Dirichlet by normalizing independent Gamma draws (k shape, 1 scale)."""
    gammas = [random.gammavariate(a if a > 0 else 1e-6, 1.0) for a in alphas]
    total = sum(gammas) or 1.0
    return [g / total for g in gammas]


def _normalize(values: list[float]) -> list[float]:
    s = float(sum(values))
    if s <= 0:
        n = len(values)
        return [1.0 / max(1, n)] * n
    return [v / s for v in values]


def _clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


# ------------- Attendance generation -------------

def _choose_topics(events: list[dict], topic_count: int) -> tuple[list[str], dict[str, str]]:
    """Return (topics, event_id_to_topic) using top categories as topics.

    If unique categories < topic_count, pad with synthetic topics.
    """
    # Count categories
    counts: dict[str, int] = {}
    for ev in events:
        c = (ev.get("category") or "Misc").strip() or "Misc"
        counts[c] = counts.get(c, 0) + 1

    # Top categories by frequency
    sorted_cats = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    top = [c for c, _ in sorted_cats[:max(1, topic_count)]]
    # Pad to topic_count
    while len(top) < topic_count:
        top.append(f"Topic {len(top)+1}")

    # Map events to closest topic (use category if in top; otherwise bucket by hash)
    event_to_topic: dict[str, str] = {}
    for ev in events:
        eid = ev["id"]
        cat = (ev.get("category") or "Misc").strip() or "Misc"
        if cat in top:
            event_to_topic[eid] = cat
        else:
            # Stable bucket into one of the topics
            idx = (hash(eid) % len(top)) if len(top) else 0
            event_to_topic[eid] = top[idx]
    return top, event_to_topic


def _make_biased_attendance(
    user_ids: list[str],
    events: list[dict],
    *,
    topic_count: int = 6,
    target_events: int = 30,
) -> list[dict]:
    if not user_ids or not events:
        return []

    # Select a subset of events
    if len(events) > target_events:
        events = random.sample(events, k=target_events)

    topics, event_to_topic = _choose_topics(events, topic_count)

    # Global topic popularity (spiky -> discrepancies visible)
    # Smaller alpha -> spikier distribution
    topic_global_weights = _dirichlet([0.6] * len(topics))
    topic_to_weight = {t: w for t, w in zip(topics, topic_global_weights)}

    # Per-event popularity (heavy-tailed) modulated by topic popularity
    # lognormal with sigma=1.0 gives a decent spread; multiply by topic weight
    event_popularity_raw: dict[str, float] = {}
    for ev in events:
        eid = ev["id"]
        t = event_to_topic[eid]
        # lognormal(mean=0, sigma=1.0)
        base = random.lognormvariate(0.0, 1.0)
        event_popularity_raw[eid] = base * (0.5 + 1.5 * topic_to_weight.get(t, 0.0))

    # Normalize popularity for convenience
    max_pop = max(event_popularity_raw.values()) if event_popularity_raw else 1.0
    event_popularity_norm = {eid: (w / max_pop if max_pop > 0 else 0.0) for eid, w in event_popularity_raw.items()}

    # User activity (some users much more active than others)
    user_activity: dict[str, float] = {uid: random.lognormvariate(-0.2, 0.8) for uid in user_ids}

    # User topic preferences (skewed)
    # Use low concentration to create clear favorites
    user_topic_pref: dict[str, dict[str, float]] = {}
    for uid in user_ids:
        pref_vec = _dirichlet([0.5] * len(topics))
        user_topic_pref[uid] = {t: w for t, w in zip(topics, pref_vec)}

    # Smooth preferences along friendship graph to align clusters
    try:
        friend_beta = float(os.getenv("ATT_PREF_FRIEND_BETA", "0.35"))
    except Exception:
        friend_beta = 0.35
    try:
        friend_steps = int(os.getenv("ATT_PREF_FRIEND_STEPS", "2"))
    except Exception:
        friend_steps = 2
    if friend_beta > 0 and friend_steps > 0:
        adjacency = _load_friendships_adjacency()
        user_topic_pref = _smooth_preferences_with_friends(
            user_ids,
            topics,
            user_topic_pref,
            adjacency,
            beta=friend_beta,
            steps=friend_steps,
        )

    # Determine attendance per event by ranking users with an affinity score
    records: list[dict] = []
    for ev in events:
        eid = ev["id"]
        t = event_to_topic[eid]
        pop = event_popularity_norm.get(eid, 0.0)
        # Target attendee fraction per event between ~10% and ~60% depending on pop
        target_fraction = 0.10 + 0.50 * pop
        target_attendees = max(2, min(len(user_ids) - 1, int(round(len(user_ids) * target_fraction))))

        # Score each user for this event
        scored: list[tuple[str, float]] = []
        for uid in user_ids:
            topic_aff = user_topic_pref[uid].get(t, 0.0)
            act = user_activity[uid]
            # Score composition: activity x topic affinity x event popularity, with floors
            score = (0.2 + 0.8 * act) * (0.2 + 0.8 * topic_aff) * (0.2 + 0.8 * pop)
            # Add small noise to avoid ties
            score += random.random() * 1e-3
            scored.append((uid, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        attendees = [uid for uid, _ in scored[:target_attendees]]

        # Assign RSVP status based on affinity; visibility override mostly None
        for uid in attendees:
            topic_aff = user_topic_pref[uid].get(t, 0.0)
            p_going = _clamp(0.45 + 0.45 * topic_aff, 0.10, 0.95)
            r = random.random()
            status = "going" if r < p_going else "declined"

            vis_draw = random.random()
            if vis_draw < 0.70:
                vis = None
            elif vis_draw < 0.85:
                vis = "all"
            elif vis_draw < 0.95:
                vis = "friends"
            else:
                vis = "ghost"

            records.append({
                "id": f"{uid}|{eid}",
                "user_id": uid,
                "event_id": eid,
                "rsvp_status": status,
                "visibility_override": vis,
            })

        # Optionally sprinkle a few explicit declines among top non-attendees for realism
        non_attendees = [uid for uid, _ in scored[target_attendees:target_attendees + max(0, int(0.05 * len(user_ids)))] ]
        for uid in non_attendees:
            if random.random() < 0.35:  # not too many
                records.append({
                    "id": f"{uid}|{eid}",
                    "user_id": uid,
                    "event_id": eid,
                    "rsvp_status": "declined",
                    "visibility_override": None,
                })

    # Deduplicate by id (user|event)
    dedup = {r["id"]: r for r in records}
    return list(dedup.values())


def main() -> None:
    seed_val = int(os.getenv("FAKE_SEED", "42"))
    random.seed(seed_val)

    # Load events first to infer counts from seed if env overrides are not set
    events = _load_events_with_meta()
    if not events:
        # Without events, we cannot produce attendance
        print("No amiv_events.json or vis_events.json found; no attendance generated.")
        return

    # Seed-derived defaults
    seed_user_ids_all = _load_all_user_ids()
    inferred_user_count = len(seed_user_ids_all) if seed_user_ids_all else 100
    inferred_event_count = len(events)
    inferred_topic_count = max(1, len({(ev.get("category") or "Misc").strip() or "Misc" for ev in events}))

    # Env overrides (if provided)
    user_target = int(os.getenv("ATT_USER_COUNT", str(inferred_user_count)))
    event_target = int(os.getenv("ATT_EVENT_COUNT", str(inferred_event_count)))
    topic_count = int(os.getenv("ATT_TOPIC_COUNT", str(inferred_topic_count)))

    # Load users (sample down to target if needed)
    users = _load_users(user_target)
    user_ids = [str(u.get("id")) for u in users if u.get("id")]

    attendance = _make_biased_attendance(user_ids, events, topic_count=topic_count, target_events=event_target)

    out_dir = _seed_dir()
    out_path = out_dir / "attendance.gen.json"
    out_path.write_text(json.dumps(attendance, indent=2, ensure_ascii=False))

    # Quick summary
    unique_events = len({r["event_id"] for r in attendance})
    unique_users = len({r["user_id"] for r in attendance})
    status_counts: dict[str, int] = {}
    for r in attendance:
        s = str(r.get("rsvp_status") or "").lower()
        status_counts[s] = status_counts.get(s, 0) + 1
    print(
        f"Wrote attendance={len(attendance)} records across users={unique_users}, events={unique_events} to {out_path}\n"
        f"Status mix: {status_counts}"
    )


if __name__ == "__main__":
    main()


