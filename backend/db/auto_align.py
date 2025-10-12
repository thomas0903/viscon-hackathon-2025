from __future__ import annotations

import sqlite3
import subprocess
from pathlib import Path


def _db_path_from_alembic() -> Path:
    # Read backend/alembic.ini for sqlite url; resolve relative to that file
    cfg_path = Path(__file__).resolve().parents[1] / "alembic.ini"  # backend/alembic.ini
    url = "sqlite:///var/data/app.db"
    try:
        text = cfg_path.read_text()
        for line in text.splitlines():
            if line.strip().lower().startswith("sqlalchemy.url"):
                _, val = line.split("=", 1)
                url = val.strip()
                break
    except Exception:
        pass
    if url.startswith("sqlite") and ":///" in url:
        path = url.split(":///", 1)[1]
        if path.startswith("/"):
            return Path(path)
        return (cfg_path.parent / path).resolve()
    raise RuntimeError("Unsupported DATABASE_URL for auto-align; expected sqlite")


def auto_align() -> None:
    """Align the DB to our expected schema.

    - If DB missing: nothing to do.
    - If tables exist but no alembic_version: stamp initial.
    - If schema is incompatible (e.g., integer ids instead of string), remove DB to rebuild.
    """
    try:
        db_path = _db_path_from_alembic()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        if not db_path.exists():
            return  # nothing to align

        def _column_type(conn: sqlite3.Connection, table: str, column: str) -> str | None:
            try:
                cur = conn.execute(f"PRAGMA table_info({table})")
                for cid, name, ctype, notnull, dflt, pk in cur.fetchall():
                    if name == column:
                        return (ctype or "").upper()
            except sqlite3.Error:
                return None
            return None

        con = sqlite3.connect(str(db_path))
        try:
            cur = con.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
            users_exists = cur.fetchone() is not None
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='events'")
            events_exists = cur.fetchone() is not None

            # If incompatible types detected, remove DB to allow clean migration
            incompatible = False
            if users_exists:
                t = _column_type(con, "users", "id")
                if t and t not in ("TEXT", "VARCHAR", "NVARCHAR"):
                    incompatible = True
            if events_exists:
                t = _column_type(con, "events", "id")
                if t and t not in ("TEXT", "VARCHAR", "NVARCHAR"):
                    incompatible = True
            if incompatible:
                try:
                    con.close()
                except Exception:
                    pass
                db_path.unlink(missing_ok=True)
                return

            # does alembic_version exist and have a row?
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version'")
            alembic_exists = cur.fetchone() is not None
            has_version = False
            if alembic_exists:
                try:
                    cur.execute("SELECT COUNT(1) FROM alembic_version")
                    cnt_row = cur.fetchone()
                    has_version = (cnt_row[0] if cnt_row else 0) > 0
                except sqlite3.Error:
                    has_version = False
            if users_exists and not has_version:
                subprocess.run(["alembic", "-c", "alembic.ini", "stamp", "0001_int_initial"], check=True)
        finally:
            con.close()
    except Exception:
        # Non-fatal; better to proceed and let upgrade run
        pass


if __name__ == "__main__":
    auto_align()
