#!/usr/bin/env python3
import json
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
import hashlib

import networkx as nx
from faker import Faker

# Optional heavy-tail fitting (metrics only; no visualization)
try:
    import powerlaw
    HAS_POWERLAW = True
except Exception:
    HAS_POWERLAW = False

# -------------------
# Parameters
# -------------------
N_USERS = 200
AVG_DEG = 12          # LFR target average degree
MU = 0.2              # LFR mixing parameter
TAU1 = 2.5            # LFR degree exponent
TAU2 = 1.5            # LFR community-size exponent
WS_K = 10             # WS fallback: neighbors
WS_P = 0.1            # WS fallback: rewiring probability

# Assortativity tuning
ASSORTATIVITY_TARGET = 0.05     # aim for r >= 0.05
CLUSTERING_FLOOR_RATIO = 0.85   # keep C >= 85% of pre-rewire C
REWIRE_MAX_ITERS = 15000        # proposals to try
REWIRE_BATCH = 1                # swaps per proposal
SEED = 42

random.seed(SEED)

# -------------------
# Seed output helpers
# -------------------
def _seed_dir() -> Path:
    return Path("db/seed_data") if Path("db/seed_data").exists() else Path("backend/db/seed_data")


def _load_cached_users() -> list[dict] | None:
    try:
        p = _seed_dir() / "users.gen.json"
        if not p.exists():
            return None
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, list) and all(isinstance(x, dict) for x in data):
            return data
    except Exception:
        return None
    return None


# -------------------
# Avatar URL helpers (no downloads)
# -------------------
def _remote_avatar_url_for_username(username: str) -> str:
    seed = hashlib.sha1(username.encode("utf-8")).hexdigest()
    return f"https://i.pravatar.cc/256?u={seed}"


def _ensure_remote_avatar_for_user(user: dict) -> bool:
    """Ensure user has a remote profile_picture_url (no local files). Returns True if modified."""
    username = str(user.get("username") or user.get("id") or "").strip()
    if not username:
        return False
    remote_url = _remote_avatar_url_for_username(username)
    if user.get("profile_picture_url") != remote_url:
        user["profile_picture_url"] = remote_url
        return True
    return False


# -------------------
# Generation
# -------------------
def build_graph(n: int = N_USERS) -> nx.Graph:
    # Prefer LFR for realism; fallback to connected WS for robustness
    try:
        G = nx.generators.community.LFR_benchmark_graph(
            n=n, tau1=TAU1, tau2=TAU2, mu=MU, average_degree=AVG_DEG, seed=SEED
        )
        if not nx.is_connected(G):
            G = G.subgraph(max(nx.connected_components(G), key=len)).copy()
        return G
    except Exception:
        return nx.generators.random_graphs.connected_watts_strogatz_graph(
            n=n, k=WS_K, p=WS_P, tries=100, seed=SEED
        )


def make_unique_user_ids(n: int) -> list[str]:
    fake = Faker("de_DE")
    seen: set[str] = set()
    ids: list[str] = []

    def norm(s: str) -> str:
        return s.replace(" ", "").replace("'", "").lower()

    for _ in range(n):
        first = fake.first_name()
        last = fake.last_name()
        base = norm((first[:1] + last))
        cand, suf = base, 2
        while cand in seen:
            cand = f"{base}{suf}"
            suf += 1
        seen.add(cand)
        ids.append(cand)
    return ids


def make_users(n: int) -> list[dict]:
    fake = Faker("de_DE")
    seen: set[str] = set()
    users: list[dict] = []

    def norm(s: str) -> str:
        return s.replace(" ", "").replace("'", "").lower()

    for _ in range(n):
        first = fake.first_name()
        last = fake.last_name()
        base = norm((first[:1] + last))
        cand, suf = base, 2
        while cand in seen:
            cand = f"{base}{suf}"
            suf += 1
        seen.add(cand)
        visibility_mode = random.choice(["all", "friends", "ghost"])  # VisibilityMode
        username = cand
        user = {
            "id": cand,
            "username": username,
            "first_name": first,
            "last_name": last,
            "email": f"{cand}@example.com",
            "is_admin": False,
            "is_association": False,
            "visibility_mode": visibility_mode,
            "profile_picture_url": _remote_avatar_url_for_username(username),
        }
        users.append(user)
    return users


# -------------------
# Rewiring to increase assortativity with clustering floor
# -------------------
def increase_assortativity_connected(
    G: nx.Graph,
    target: float = ASSORTATIVITY_TARGET,
    C_floor: float | None = None,
    max_iters: int = REWIRE_MAX_ITERS,
    batch: int = REWIRE_BATCH,
    seed: int = SEED,
):
    """
    Hill-climb degree assortativity r using connected_double_edge_swap, accepting only improving proposals
    and enforcing a clustering floor to preserve small-world clustering.
    """
    rng = random.Random(seed)
    if not nx.is_connected(G):
        G = G.subgraph(max(nx.connected_components(G), key=len)).copy()
    H = G.copy()
    r_curr = nx.degree_assortativity_coefficient(H)
    C_pre = nx.average_clustering(H)
    floor = C_pre * (CLUSTERING_FLOOR_RATIO if C_floor is None else C_floor)
    if r_curr >= target:
        return H, r_curr, C_pre
    no_improve = 0
    for _ in range(max_iters):
        H2 = H.copy()
        try:
            swapped = nx.connected_double_edge_swap(
                H2, nswap=batch, _window_threshold=3, seed=rng.randint(0, 10**9)
            )
        except nx.NetworkXError:
            continue
        if swapped == 0:
            continue
        r_new = nx.degree_assortativity_coefficient(H2)
        if r_new <= r_curr:
            no_improve += 1
            continue
        C2 = nx.average_clustering(H2)
        if C2 < floor:
            # reject if clustering would drop below floor
            continue
        # accept
        H, r_curr = H2, r_new
        no_improve = 0
        if r_curr >= target:
            break
    return H, r_curr, C_pre


# -------------------
# Metrics (text only)
# -------------------
def compute_metrics(G: nx.Graph) -> dict:
    H = G.subgraph(max(nx.connected_components(G), key=len)).copy()
    C = nx.average_clustering(H)
    L = nx.average_shortest_path_length(H)
    r = nx.degree_assortativity_coefficient(H)
    from networkx.algorithms.community import greedy_modularity_communities, quality

    comms = list(greedy_modularity_communities(H))
    Q = quality.modularity(H, comms)
    tri = sum(nx.triangles(H).values()) // 3
    trans = nx.transitivity(H)
    # Degree-preserving null
    deg_seq = [d for _, d in H.degree()]
    CM = nx.configuration_model(deg_seq, seed=SEED)
    CM = nx.Graph(CM)
    CM.remove_edges_from(nx.selfloop_edges(CM))
    CM_H = CM.subgraph(max(nx.connected_components(CM), key=len)).copy()
    C_null = nx.average_clustering(CM)
    L_null = nx.average_shortest_path_length(CM_H)
    # Optional tail fit
    pl = None
    if HAS_POWERLAW:
        deg = [d for _, d in H.degree() if d > 0]
        if len(deg) >= 20:
            fit = powerlaw.Fit(deg, discrete=True, verbose=False)
            alpha = fit.power_law.alpha
            xmin = fit.power_law.xmin
            R, p_lr = fit.distribution_compare("power_law", "lognormal")
            pl = {"alpha": alpha, "xmin": xmin, "LR_power_vs_lognorm": R, "p_value": p_lr}
    return {
        "n": H.number_of_nodes(),
        "m": H.number_of_edges(),
        "C": C,
        "L": L,
        "C_null": C_null,
        "L_null": L_null,
        "C_ratio": C / C_null if C_null > 0 else float("inf"),
        "L_ratio": L / L_null if L_null > 0 else float("inf"),
        "assortativity_r": r,
        "modularity_Q": Q,
        "communities": len(comms),
        "triangles": tri,
        "transitivity": trans,
        "powerlaw": pl,
    }


# -------------------
# Main
# -------------------
def main() -> None:
    # 0) Try to load cached users; if present, reuse and ensure remote avatar URLs
    cached_users = _load_cached_users()
    users_modified = False
    if cached_users is not None:
        for u in cached_users:
            if _ensure_remote_avatar_for_user(u):
                users_modified = True
        users = cached_users
        n_users = len(users)
    else:
        users = None
        n_users = N_USERS

    # 1) Build initial graph sized to user count
    G0 = build_graph(n_users)
    if not all(isinstance(u, int) for u in G0.nodes()):
        G0 = nx.relabel_nodes(G0, {u: i for i, u in enumerate(G0.nodes())}, copy=True)

    # 2) Increase assortativity while preserving clustering
    G, r_final, C_pre = increase_assortativity_connected(G0)

    # 3) Create or reuse users and mapping
    if users is None:
        users = make_users(G.number_of_nodes())
        users_modified = True

    node_to_uid = {n: users[i]["id"] for i, n in enumerate(G.nodes())}

    # 4) Build friendships records
    deg = dict(G.degree())
    now = datetime.now(timezone.utc)
    records: list[dict] = []
    for u, v in G.edges():
        uid_u = node_to_uid[u]
        uid_v = node_to_uid[v]
        a, b = sorted([uid_u, uid_v])
        du, dv = deg[u], deg[v]
        requester = uid_u if random.random() < (du / (du + dv)) else uid_v
        ts = now - timedelta(
            days=random.randint(0, 365),
            seconds=random.randint(0, 24 * 3600 - 1),
            microseconds=random.randint(0, 999_999),
        )
        records.append({
            "id": f"{a}|{b}",
            "user_id": uid_u,
            "friend_id": uid_v,
            "requester_id": requester,
            "status": "accepted",
            "accepted_at": ts.isoformat(timespec="microseconds"),
        })

    # 5) Write seed JSON files (cache-aware: only write users if created/updated)
    out = _seed_dir()
    out.mkdir(parents=True, exist_ok=True)
    if cached_users is None or users_modified:
        (out / "users.gen.json").write_text(json.dumps(users, ensure_ascii=False, indent=2))
    (out / "friendships.gen.json").write_text(json.dumps(records, ensure_ascii=False, indent=2))
    if cached_users is None or users_modified:
        print(f"Wrote users={len(users)}, friendships={len(records)} to {out}")
    else:
        print(f"Reused users={len(users)}; wrote friendships={len(records)} to {out}")

    # 6) Metrics (text only; no visualization)
    metrics = compute_metrics(G)
    print("\n--- Graph Metrics (post-rewire) ---", file=sys.stderr)
    for k, v in metrics.items():
        if k == "powerlaw":
            print(f"{k}: {v}", file=sys.stderr)
        else:
            print(f"{k}: {v:.6f}" if isinstance(v, float) else f"{k}: {v}", file=sys.stderr)

    # 7) Targets guidance
    print("\n--- Target Guidance ---", file=sys.stderr)
    print("Small-world: C >> C_null and L ≈ L_null (high clustering with short paths).", file=sys.stderr)
    print("Assortativity: r > 0 (social networks are typically degree-assortative).", file=sys.stderr)
    print("Communities: modularity Q > 0 with multiple cohesive groups.", file=sys.stderr)
    print("Triadic closure: high triangles/transitivity vs degree-preserving null.", file=sys.stderr)


if __name__ == "__main__":
    main()


