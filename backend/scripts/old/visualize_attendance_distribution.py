from __future__ import annotations

"""
Visualize distributions from attendance.gen.json:
 - Top events by 'going' counts
 - Category totals ('going' per category)
 - Histogram of 'going' per user

Usage (repo root or backend/):
  python backend/scripts/visualize_attendance_distribution.py

Outputs PNGs in var/graphs/; falls back to CSVs if Matplotlib is unavailable.
"""

import json
import os
from pathlib import Path
from typing import Iterable


def _seed_dirs() -> list[Path]:
    bases = [
        Path("backend/db/seed_data"),
        Path("db/seed_data"),
        Path("backend/scripts/backend/db/seed_data"),
    ]
    out: list[Path] = []
    seen: set[str] = set()
    for b in bases:
        try:
            if b.exists():
                rb = str(b.resolve())
                if rb not in seen:
                    out.append(b.resolve())
                    seen.add(rb)
        except Exception:
            continue
    return out


def _load_attendance() -> list[dict]:
    for base in _seed_dirs():
        f = (base / "attendance.gen.json").resolve()
        try:
            if f.exists():
                data = json.loads(f.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    return [x for x in data if isinstance(x, dict)]
        except Exception:
            continue
    return []


def _load_events_meta() -> dict[str, dict]:
    """Return mapping event_id -> {name, category} from events*.json files."""
    items: dict[str, dict] = {}
    for base in _seed_dirs():
        for jf in base.glob("events*.json"):
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
                if eid in items:
                    continue
                items[eid] = {
                    "name": str(ev.get("name") or eid),
                    "category": (str(ev.get("category") or "Misc").strip() or "Misc"),
                }
    return items


def _ensure_outdir() -> Path:
    out = Path("var/graphs")
    out.mkdir(parents=True, exist_ok=True)
    return out


def _plot_or_csv_top_events(event_go_counts: dict[str, int], event_meta: dict[str, dict], out_dir: Path, top_n: int = 20) -> None:
    ranked = sorted(event_go_counts.items(), key=lambda kv: kv[1], reverse=True)[:top_n]
    labels = [event_meta.get(eid, {}).get("name", eid) for eid, _ in ranked]
    values = [v for _, v in ranked]
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig = plt.figure(figsize=(12, 6), dpi=160)
        ax = plt.gca()
        ax.bar(range(len(values)), values, color="#4e79a7")
        ax.set_xticks(range(len(values)))
        # Truncate long labels
        trunc = [l if len(l) <= 18 else (l[:15] + "…") for l in labels]
        ax.set_xticklabels(trunc, rotation=35, ha="right")
        ax.set_ylabel("Going count")
        ax.set_title("Top events by 'going'")
        plt.tight_layout(pad=1.0)
        fig.savefig(out_dir / "attendance_top_events.png")
        plt.close(fig)
    except Exception:
        # Fallback to CSV
        lines = ["event_id,event_name,going_count"]
        for (eid, c), name in zip(ranked, labels):
            safe_name = name.replace(",", " ")
            lines.append(f"{eid},{safe_name},{c}")
        (out_dir / "attendance_top_events.csv").write_text("\n".join(lines), encoding="utf-8")


def _plot_or_csv_categories(cat_go_counts: dict[str, int], out_dir: Path) -> None:
    cats = sorted(cat_go_counts.keys())
    vals = [cat_go_counts[c] for c in cats]
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig = plt.figure(figsize=(10, 5), dpi=160)
        ax = plt.gca()
        ax.bar(range(len(vals)), vals, color="#59a14f")
        ax.set_xticks(range(len(vals)))
        ax.set_xticklabels(cats, rotation=25, ha="right")
        ax.set_ylabel("Going count")
        ax.set_title("Going by category")
        plt.tight_layout(pad=1.0)
        fig.savefig(out_dir / "attendance_categories.png")
        plt.close(fig)
    except Exception:
        lines = ["category,going_count"]
        for c in cats:
            lines.append(f"{c},{cat_go_counts[c]}")
        (out_dir / "attendance_categories.csv").write_text("\n".join(lines), encoding="utf-8")


def _plot_or_csv_user_hist(user_go_counts: dict[str, int], out_dir: Path) -> None:
    vals = list(user_go_counts.values())
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np

        fig = plt.figure(figsize=(10, 5), dpi=160)
        ax = plt.gca()
        bins = min(20, max(3, int(len(vals) ** 0.5)))
        ax.hist(vals, bins=bins, color="#e15759", edgecolor="#ffffff")
        ax.set_xlabel("'Going' events per user")
        ax.set_ylabel("Users")
        ax.set_title("Distribution of user attendance")
        plt.tight_layout(pad=1.0)
        fig.savefig(out_dir / "attendance_user_hist.png")
        plt.close(fig)
    except Exception:
        lines = ["user_id,going_count"]
        for uid, c in sorted(user_go_counts.items(), key=lambda kv: kv[1], reverse=True):
            lines.append(f"{uid},{c}")
        (out_dir / "attendance_user_counts.csv").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    top_n = int(os.getenv("VIS_TOP_EVENTS", "20"))

    attendance = _load_attendance()
    if not attendance:
        print("No attendance.gen.json found; nothing to visualize.")
        return
    events_meta = _load_events_meta()
    out_dir = _ensure_outdir()

    # Aggregate counts
    event_go: dict[str, int] = {}
    cat_go: dict[str, int] = {}
    user_go: dict[str, int] = {}

    for rec in attendance:
        status = str(rec.get("rsvp_status") or "").lower()
        if status != "going":
            continue
        eid = str(rec.get("event_id") or "").strip()
        uid = str(rec.get("user_id") or "").strip()
        if not eid or not uid:
            continue
        event_go[eid] = event_go.get(eid, 0) + 1
        user_go[uid] = user_go.get(uid, 0) + 1
        cat = events_meta.get(eid, {}).get("category", "Misc")
        cat_go[cat] = cat_go.get(cat, 0) + 1

    _plot_or_csv_top_events(event_go, events_meta, out_dir, top_n=top_n)
    _plot_or_csv_categories(cat_go, out_dir)
    _plot_or_csv_user_hist(user_go, out_dir)

    print(f"Wrote visualizations to {out_dir}")


if __name__ == "__main__":
    main()


