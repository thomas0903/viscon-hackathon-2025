from __future__ import annotations

"""
Generate JSON seed for users, friendships, and attendance based on events JSON.
Usage (repo root or backend/):
  python backend/scripts/generate_social_data.py
Outputs: backend/db/seed_data/{users.gen.json,friendships.gen.json,attendance.gen.json}
"""

import os
import random
from datetime import datetime, timezone
from typing import Iterable
from pathlib import Path
import hashlib
import json
import requests
import itertools
import os as _os


def _seed_dir() -> Path:
    return Path("db/seed_data") if Path("db/seed_data").exists() else Path("backend/db/seed_data")


def _avatars_root() -> Path:
    # Always use application upload root; create as needed
    return Path("var/uploads/user")


def _download_avatar(url: str, dest_dir: Path) -> str | None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    try:
        r = requests.get(url, timeout=20)
    except Exception:
        return None
    if r.status_code != 200:
        return None
    ctype = r.headers.get("Content-Type", "").split(";")[0].lower()
    ext = {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
    }.get(ctype, ".jpg")
    fname = f"avatar{ext}"
    (dest_dir / fname).write_bytes(r.content)
    return fname


def _random_username(first: str, last: str, used: set[str]) -> str:
    base = (first[0] + last).lower().replace(" ", "").replace("'", "")[:16]
    candidate = base
    i = 1
    while candidate in used:
        candidate = f"{base}{i}"
        i += 1
    used.add(candidate)
    return candidate


def _assign_avatar_for_user(user: dict) -> None:
    if user.get("profile_picture_url"):
        return
    seed = hashlib.sha1((user.get("username") or user.get("id") or "user").encode("utf-8")).hexdigest()
    url = f"https://i.pravatar.cc/256?u={seed}"
    dest = _avatars_root() / str(user["id"])
    fname = _download_avatar(url, dest)
    if fname:
        user["profile_picture_url"] = f"/uploads/user/{user['id']}/{fname}"


def _get_or_create_user_by_username(username: str, **fields) -> dict:
    return {"id": username[:64], "username": username, **fields}


def _make_users(n: int) -> list[dict]:
    first_names = [
        "Alex", "Sam", "Jamie", "Taylor", "Jordan", "Casey", "Riley", "Morgan",
        "Avery", "Rowan", "Kai", "Sasha", "Quinn", "Reese", "Elliot", "Charlie",
        "Robin", "Adrian", "Noah", "Milan", "Luca", "Maya", "Nora", "Eva", "Omar",
        "Iris", "Leo", "Mira", "Felix", "Lena", "Tara", "Jonas", "Vera", "Elena",
    ]
    last_names = [
        "Müller", "Meier", "Schmid", "Keller", "Fischer", "Weber", "Huber", "Moser",
        "Baumann", "Zimmermann", "Frei", "Graf", "Koch", "Roth", "Schneider", "Suter",
        "Ammann", "Bischof", "Furrer", "Hauser", "Imhof", "Kunz", "Lehmann", "Meister",
    ]
    used_usernames: set[str] = set()
    users: list[dict] = []
    while len(users) < n:
        fn = random.choice(first_names)
        ln = random.choice(last_names)
        username = _random_username(fn, ln, used_usernames)
        u = _get_or_create_user_by_username(
            username,
            first_name=fn,
            last_name=ln,
            email=f"{username}@example.com",
            is_admin=False,
            is_association=False,
            visibility_mode=random.choice(["all", "friends", "ghost"]),
        )
        _assign_avatar_for_user(u)
        users.append(u)
    return users


def _make_friendship_record(a: str, b: str, requester: str, status: str, accepted: bool = False) -> dict:
    uid, fid = (a, b) if a < b else (b, a)
    return {
        "id": f"{uid}|{fid}",
        "user_id": uid,
        "friend_id": fid,
        "requester_id": requester,
        "status": status,
        "accepted_at": datetime.now(timezone.utc).isoformat() if accepted else None,
    }


def _assign_communities(users: list[dict], num_communities: int) -> dict[str, int]:
    """Assign users to communities to induce clusters.

    The assignment is stable for a given seed by using random choices.
    """
    if num_communities <= 1:
        return {u["id"]: 0 for u in users}
    communities = {}
    for u in users:
        # Light bias by last name initial to create more cohesive clusters
        ln = (u.get("last_name") or "").strip().lower()
        if ln:
            bucket = (ord(ln[0]) - 97) % max(1, num_communities)
            # With some probability, stick to the bucket; otherwise randomize
            c = bucket if random.random() < 0.7 else random.randrange(num_communities)
        else:
            c = random.randrange(num_communities)
        communities[u["id"]] = c
    return communities


def _compute_coattendance(attendance: list[dict]) -> dict[tuple[str, str], float]:
    """Compute pairwise co-attendance weights from attendance records.

    going counts as 1.0, interested as 0.5, declined doesn't contribute.
    Returns a symmetric map (uid,v) with uid < v.
    """
    event_to_attendees: dict[str, list[tuple[str, float]]] = {}
    for rec in attendance:
        status = str(rec.get("rsvp_status") or "").lower()
        if status not in {"going", "interested"}:
            continue
        weight = 1.0 if status == "going" else 0.5
        eid = rec["event_id"]
        event_to_attendees.setdefault(eid, []).append((rec["user_id"], weight))

    pair_weight: dict[tuple[str, str], float] = {}
    for attendees in event_to_attendees.values():
        if len(attendees) < 2:
            continue
        # For each unordered pair, add combined weight
        for (u, wu), (v, wv) in itertools.combinations(attendees, 2):
            a, b = (u, v) if u < v else (v, u)
            pair_weight[(a, b)] = pair_weight.get((a, b), 0.0) + min(wu, wv)

    # Normalize to [0, 1]
    if not pair_weight:
        return {}
    max_w = max(pair_weight.values()) or 1.0
    return {k: v / max_w for k, v in pair_weight.items()}


def _make_friendships(
    users: list[dict],
    attendance: list[dict],
    *,
    avg_degree: float = 8.0,
    homophily_weight: float = 0.6,
    closure_weight: float = 0.35,
    pref_attach_alpha: float = 1.0,
    within_comm_bonus: float = 0.5,
    same_last_name_bonus: float = 0.35,
    pending_rate: float = 0.08,
    block_rate: float = 0.03,
    num_communities: int = 4,
) -> list[dict]:
    """Generate a realistic friendship graph.

    - Community structure
    - Homophily via co-attendance and same last name
    - Triadic closure via mutual friends
    - Preferential attachment for hubs
    - Small fractions of pending and blocked edges
    """
    user_ids = [u["id"] for u in users]
    n = len(user_ids)
    if n < 2:
        return []

    # Parameters
    avg_degree = float(_os.getenv("FAKE_AVG_DEGREE", avg_degree))
    homophily_weight = float(_os.getenv("FAKE_HOMOPHILY", homophily_weight))
    closure_weight = float(_os.getenv("FAKE_CLOSURE", closure_weight))
    pref_attach_alpha = float(_os.getenv("FAKE_PREF_ATTACH", pref_attach_alpha))
    within_comm_bonus = float(_os.getenv("FAKE_WITHIN_COMMUNITY_BONUS", within_comm_bonus))
    same_last_name_bonus = float(_os.getenv("FAKE_SAME_LAST_NAME_BONUS", same_last_name_bonus))
    pending_rate = float(_os.getenv("FAKE_PENDING_RATE", pending_rate))
    block_rate = float(_os.getenv("FAKE_BLOCK_RATE", block_rate))
    num_communities = int(_os.getenv("FAKE_COMMUNITIES", num_communities))

    target_accepted_edges = max(1, int(n * avg_degree / 2))

    # Precompute
    communities = _assign_communities(users, num_communities)
    coatt = _compute_coattendance(attendance)  # pair -> [0,1]
    last_name_of = {u["id"]: (u.get("last_name") or "").strip().lower() for u in users}

    # Graph state
    neighbors: dict[str, set[str]] = {u: set() for u in user_ids}
    degrees: dict[str, int] = {u: 0 for u in user_ids}
    existing_pairs: set[tuple[str, str]] = set()

    def pair(u: str, v: str) -> tuple[str, str]:
        return (u, v) if u < v else (v, u)

    def mutual_count(u: str, v: str) -> int:
        if not neighbors[u] or not neighbors[v]:
            return 0
        # Iterate over smaller set for efficiency
        a, b = (u, v) if len(neighbors[u]) < len(neighbors[v]) else (v, u)
        return sum(1 for x in neighbors[a] if x in neighbors[b])

    # Ensure initial connectivity by creating a light ring
    ring = user_ids[:]
    random.shuffle(ring)
    for i in range(n):
        u = ring[i]
        v = ring[(i + 1) % n]
        a, b = pair(u, v)
        if (a, b) in existing_pairs:
            continue
        existing_pairs.add((a, b))
        neighbors[a].add(b)
        neighbors[b].add(a)
        degrees[a] += 1
        degrees[b] += 1

    accepted_records: list[dict] = []
    # Convert ring edges to accepted edges
    for (a, b) in list(existing_pairs):
        requester = random.choice([a, b])
        accepted_records.append(_make_friendship_record(a, b, requester=requester, status="accepted", accepted=True))

    # Add remaining accepted edges using weighted selection
    def candidate_score(u: str, v: str) -> float:
        base = 1e-3  # avoid zero weights
        # Co-attendance homophily
        w_co = coatt.get(pair(u, v), 0.0)
        base += homophily_weight * w_co
        # Community and last name
        if communities.get(u) == communities.get(v):
            base += within_comm_bonus
        if last_name_of.get(u) and last_name_of.get(u) == last_name_of.get(v):
            base += same_last_name_bonus
        # Triadic closure
        mc = mutual_count(u, v)
        if mc:
            base += closure_weight * mc
        # Preferential attachment to hubs
        base += max(0.0, float((degrees[v] + 1) ** pref_attach_alpha))
        return base

    while len(accepted_records) < target_accepted_edges:
        # Prefer nodes under target degree
        deg_target = max(1.0, avg_degree)
        weights = []
        for u in user_ids:
            w = max(0.2, (deg_target - degrees[u]))
            weights.append((u, w))
        total_w = sum(w for _, w in weights)
        r = random.random() * total_w
        cumulative = 0.0
        u = user_ids[0]
        for cand, w in weights:
            cumulative += w
            if r <= cumulative:
                u = cand
                break

        # Build candidate list for u
        candidates = [v for v in user_ids if v != u and pair(u, v) not in existing_pairs]
        if not candidates:
            # Graph saturated for this node; try another
            if len(existing_pairs) >= n * (n - 1) // 2:
                break  # complete graph
            continue

        scored = [(v, candidate_score(u, v)) for v in candidates]
        # If all weights are equal/near-zero, pick uniformly at random
        ssum = sum(s for _, s in scored)
        if ssum <= 0:
            v = random.choice(candidates)
        else:
            # Weighted random choice
            target = random.random() * ssum
            acc = 0.0
            v = candidates[0]
            for cand_v, s in scored:
                acc += s
                if target <= acc:
                    v = cand_v
                    break

        a, b = pair(u, v)
        if (a, b) in existing_pairs:
            continue
        existing_pairs.add((a, b))
        neighbors[a].add(b)
        neighbors[b].add(a)
        degrees[a] += 1
        degrees[b] += 1
        requester = random.choice([a, b])
        accepted_records.append(
            _make_friendship_record(a, b, requester=requester, status="accepted", accepted=True)
        )

    # Add pending and blocked edges as a small random sample of remaining pairs
    remaining_pairs = [(a, b) for a in user_ids for b in user_ids if a < b and (a, b) not in existing_pairs]
    random.shuffle(remaining_pairs)
    num_pending = int(len(accepted_records) * pending_rate)
    num_blocked = int(len(accepted_records) * block_rate)
    pending_records: list[dict] = []
    blocked_records: list[dict] = []
    for i, (a, b) in enumerate(remaining_pairs):
        if i < num_pending:
            requester = random.choice([a, b])
            pending_records.append(_make_friendship_record(a, b, requester=requester, status="pending", accepted=False))
        elif i < num_pending + num_blocked:
            requester = random.choice([a, b])
            blocked_records.append(_make_friendship_record(a, b, requester=requester, status="blocked", accepted=False))
        else:
            break

    records = accepted_records + pending_records + blocked_records
    # Dedup for safety
    dedup = {rec["id"]: rec for rec in records}
    return list(dedup.values())


def _load_event_ids() -> list[str]:
    ids: list[str] = []
    sd = _seed_dir()
    # Search both main seed directory and scripts' scraped events directory
    candidates: list[Path] = []
    for p in [
        sd,
        Path("backend/db/seed_data"),
        Path("db/seed_data"),
        Path("scripts/backend/db/seed_data"),
        (Path(__file__).parent / "backend/db/seed_data"),
    ]:
        try:
            if p.exists():
                candidates.append(p.resolve())
        except Exception:
            continue
    # Deduplicate
    seen_dirs = set()
    unique_dirs: list[Path] = []
    for p in candidates:
        if str(p) in seen_dirs:
            continue
        seen_dirs.add(str(p))
        unique_dirs.append(p)

    for base in unique_dirs:
        for jf in base.glob("events*.json"):
            try:
                data = json.loads(jf.read_text(encoding="utf-8"))
            except Exception:
                continue
            items = data.get("events") if isinstance(data, dict) else data
            if not isinstance(items, list):
                continue
            for ev in items:
                if not isinstance(ev, dict):
                    continue
                src = str(ev.get("source") or "").strip()
                ext = str(ev.get("external_id") or "").strip()
                if not src or not ext:
                    continue
                ids.append((f"{src}:{ext}")[:64])
    seen = set()
    out = []
    for x in ids:
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


def _make_attendance(user_ids: list[str], event_ids: list[str]) -> list[dict]:
    records: list[dict] = []
    if not event_ids:
        return records
    for eid in event_ids:
        k = max(5, int(len(user_ids) * random.uniform(0.2, 0.5)))
        attendees = random.sample(user_ids, k=k if k < len(user_ids) else len(user_ids))
        for uid in attendees:
            r = random.random()
            if r < 0.6:
                status = "going"
            elif r < 0.9:
                status = "interested"
            else:
                status = "declined"
            vis = random.choice([None, "all", "friends", "ghost"])
            records.append({
                "id": f"{uid}|{eid}",
                "user_id": uid,
                "event_id": eid,
                "rsvp_status": status,
                "visibility_override": vis,
            })
    dedup = {rec["id"]: rec for rec in records}
    return list(dedup.values())


def _truthy_env(name: str, default: bool = False) -> bool:
    val = str(os.getenv(name, str(default))).strip().lower()
    return val in {"1", "true", "yes", "y", "on"}


def _render_friendships_png(
    users: list[dict],
    friendships: list[dict],
    *,
    output_path: Path,
    communities_hint: dict[str, int] | None = None,
) -> None:
    """Render an undirected friendship graph to a PNG. Falls back to edgelist if Matplotlib is missing.

    Only accepted friendships are rendered as edges.
    """
    try:
        import matplotlib
        matplotlib.use("Agg")  # headless rendering
        import matplotlib.pyplot as plt
        import networkx as nx
    except Exception as e:
        try:
            import networkx as nx  # for fallback write
        except Exception:
            print("[render] Skipping: networkx not available")
            return
        # Fallback: write edgelist for external viewers (e.g., Gephi can import)
        G = nx.Graph()
        uids = [u["id"] for u in users]
        G.add_nodes_from(uids)
        for r in friendships:
            if str(r.get("status")) != "accepted":
                continue
            a = str(r.get("user_id"))
            b = str(r.get("friend_id"))
            if a and b:
                G.add_edge(a, b)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        edgelist_path = output_path.with_suffix(".edgelist")
        try:
            nx.write_edgelist(G, edgelist_path, data=False)
            print(f"[render] Matplotlib not installed; wrote edgelist to {edgelist_path}")
        except Exception as werr:
            print(f"[render] Failed to write edgelist: {werr}")
        return

    # Build graph
    G = nx.Graph()
    uids = [u["id"] for u in users]
    G.add_nodes_from(uids)
    for r in friendships:
        if str(r.get("status")) != "accepted":
            continue
        a = str(r.get("user_id"))
        b = str(r.get("friend_id"))
        if a and b:
            G.add_edge(a, b)

    # Size by degree
    deg = dict(G.degree())
    max_deg = max(deg.values()) if deg else 1
    node_sizes = [16 + 28 * (deg.get(n, 0) / max_deg) ** 0.8 for n in G.nodes()]

    # Colors by community if provided; otherwise a neutral color
    colors: list[tuple] = []
    if communities_hint:
        try:
            import numpy as _np  # not strictly required; only for colormap convenience
        except Exception:
            _np = None  # type: ignore
        import math as _math
        # Assign distinct colors via tab20 colormap
        import matplotlib.pyplot as plt  # type: ignore
        cmap = plt.cm.get_cmap("tab20")
        # Normalize community IDs to 0..k-1
        comm_ids = sorted(set(communities_hint.get(n, 0) for n in G.nodes()))
        id_to_idx = {cid: i for i, cid in enumerate(comm_ids)}
        k = max(1, len(comm_ids))
        for n in G.nodes():
            idx = id_to_idx.get(communities_hint.get(n, 0), 0)
            colors.append(cmap((idx + 0.5) / k))
    else:
        colors = [(0.31, 0.48, 0.65, 1.0) for _ in G.nodes()]  # bluish

    # Layout
    pos = {}
    try:
        pos = nx.spring_layout(G, k=1.2 / max(1, len(G)) ** 0.5, seed=42)
    except Exception:
        pos = nx.random_layout(G, seed=42)

    # Draw
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig = plt.figure(figsize=(10, 10), dpi=180)
    ax = plt.gca()
    ax.set_axis_off()
    nx.draw_networkx_edges(G, pos, width=0.4, alpha=0.22, edge_color="#9aa5b1")
    nx.draw_networkx_nodes(G, pos, node_size=node_sizes, node_color=colors, linewidths=0.4, edgecolors="#ffffff")
    plt.tight_layout(pad=0)
    try:
        fig.savefig(output_path)
        print(f"[render] Wrote friendships graph to {output_path} (nodes={len(G)}, edges={G.number_of_edges()})")
    except Exception as serr:
        print(f"[render] Failed to save graph PNG: {serr}")
    finally:
        plt.close(fig)


def main() -> None:
    seed_val = int(os.getenv("FAKE_SEED", "42"))
    random.seed(seed_val)
    count = int(os.getenv("FAKE_USER_COUNT", "40"))

    event_ids = _load_event_ids()
    users = _make_users(count)
    user_ids = [u["id"] for u in users]
    # Generate attendance first so friendships can leverage co-attendance
    attendance = _make_attendance(user_ids, event_ids)
    friendships = _make_friendships(
        users,
        attendance,
    )

    # Optional: render a PNG of friendships
    if _truthy_env("FAKE_RENDER_GRAPH", False):
        # Recompute communities for coloring (best-effort, may differ slightly)
        try:
            num_communities = int(_os.getenv("FAKE_COMMUNITIES", "4"))
        except Exception:
            num_communities = 4
        comms = _assign_communities(users, num_communities)
        img_path = Path("var/graphs/friendships.png")
        _render_friendships_png(users, friendships, output_path=img_path, communities_hint=comms)

    out = _seed_dir()
    out.mkdir(parents=True, exist_ok=True)
    (out / "users.gen.json").write_text(json.dumps(users, indent=2, ensure_ascii=False))
    (out / "friendships.gen.json").write_text(json.dumps(friendships, indent=2, ensure_ascii=False))
    (out / "attendance.gen.json").write_text(json.dumps(attendance, indent=2, ensure_ascii=False))
    print(f"Wrote users={len(users)}, friendships={len(friendships)}, attendance={len(attendance)} to {out}")


if __name__ == "__main__":
    main()
