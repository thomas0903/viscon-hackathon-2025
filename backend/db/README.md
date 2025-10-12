# Database (SQLite + SQLAlchemy + Alembic)

A lightweight, portable database layer for the project: SQLite with SQLAlchemy models, Alembic migrations, seed data, repository helpers, and optional debug endpoints. Everything is driven via the Makefile inside `backend/`.

---

## Table of Contents
- Quickstart
- Make Targets
- Code Map
- Using From FastAPI
- Schema Snapshot
- Migrations & Seeding
- Debug Endpoints
- Testing
- Docker Note
- Troubleshooting (FAQ)
- Design Notes

---

## Quickstart
1) Install dependencies
```bash
cd backend
make install
```
2) Create/upgrade schema and seed demo data
```bash
make db-upgrade
make db-seed
```
3) Run backend with debug endpoints (optional)
```bash
make run-debug
# Open docs: http://localhost:8000/api/docs
```
4) Smoke test the DB (optional)
```bash
make db-test
```

## Make Targets
```text
make install           # pip install -r requirements.txt
make db-upgrade        # auto-align + alembic upgrade head
make db-revise m="msg" # autogenerate migration from model changes
make db-seed           # migrate (if needed) + insert demo users/events/friendships/attendance
make db-reset          # wipe DB file, migrate, seed
make db-test           # run lightweight integration test with PASS/FAIL output
make run               # start backend locally
make run-debug         # start backend with /api/debug endpoints
```

## Code Map
- Engine/sessions/PRAGMAs: `backend/db/base.py`
- ORM models and enums: `backend/db/models.py`
- Alembic config: `backend/alembic.ini`
- Alembic env + migrations: `backend/db/migrations/`
- Initial migration (idempotent): `backend/db/migrations/versions/0001_int_initial.py`
- Seed + smoke check: `backend/db/seed.py`
- FastAPI session dependency: `backend/db/deps.py`
- Query helpers (repositories): `backend/db/repositories.py`
- Optional debug endpoints: `backend/db/debug_routes.py`
- Makefile (DB tasks): `backend/Makefile`

## Using From FastAPI
Inject an AsyncSession and call repository helpers.
```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from backend.db.deps import get_async_session
from backend.db.repositories import list_events

router = APIRouter(prefix="/api")

@router.get("/events")
async def events(session: AsyncSession = Depends(get_async_session)):
    rows = await list_events(session, limit=20)
    return [{"id": r.id, "name": r.name, "starts_at": r.starts_at} for r in rows]
```
Common helpers: `list_events`, `get_user_by_id`, `list_friends_for_user`, `list_attendees_for_event`, `count_attendees`.

## Schema Snapshot (integer IDs)
- `users (id int PK)`: profile, `visibility_mode`, `is_admin`, `is_association`, timestamps
- `friendships (id int PK)`: undirected pair (stored as `user_id < friend_id`), `status`
- `events (id int PK)`: schedule, location, organizer, category, `(source, external_id)`
- `event_attendance (id int PK)`: RSVP with `visibility_override`, optional `checked_in_at`
- `event_tags (event_id int + tag PK)`: simple tagging

Key constraints/indexes
- friendships: UNIQUE(user_id, friend_id), CHECK(user_id < friend_id), CHECK(valid requester)
- event_attendance: UNIQUE(user_id, event_id)
- events: UNIQUE(source, external_id); indexes on starts_at, is_public, category
- users: UNIQUE(username); indexes on visibility_mode, last_seen_at, is_association

## Migrations & Seeding
- DB URL (default): `sqlite+aiosqlite:///var/data/app.db` (when run from backend/)
- Run migrations with `make db-upgrade` (auto-aligns a pre-existing DB if needed)
- Seed demo data with `make db-seed` (this will run migrations first)
- Reset everything with `make db-reset`

The initial migration is idempotent and safe to apply even if tables already exist.

## Debug Endpoints (optional)
Enable via `ENABLE_DB_DEBUG_ROUTES=true` and start the app (e.g., `make run-debug`).
- GET `/api/debug/events`
- GET `/api/debug/users/{user_id:int}`
- GET `/api/debug/friends/{user_id:int}`
- GET `/api/debug/events/{event_id:int}/attendees?rsvp=going|interested|declined`
Use for local verification only.

## Testing
Run lightweight integration tests:
```bash
make db-test
```
What it does:
- Connects to SQLite
- Creates users, friendship, event, attendance
- Verifies attendees query
- Cleans up rows
- Prints PASS/FAIL and exits non‑zero on failure

## Docker Note
When you `docker compose up`, the backend container:
- Aligns the DB and runs migrations automatically (entrypoint)
- Uses the same path: `/app/var/data/app.db`
- Optionally seeds on start if `AUTO_SEED=true` in `docker-compose.yml`

## Troubleshooting (FAQ)
- “table already exists” after running seed first
  - `make db-reset` (wipes DB, migrates, seeds). Seed no longer creates tables
- “No module named 'backend'” when running commands
  - Run Make targets from `backend/`; PYTHONPATH is set for you
- “database is locked” under load
  - SQLite is single-writer; WAL + busy_timeout enabled. Keep a single backend instance
- “Greenlet fails to build on my Python version”
  - On Python 3.13, `greenlet` is skipped automatically. Async DB debug routes require `greenlet`, so if it’s missing they’re disabled. All core DB tasks (migrate/seed/test) work without it
- Need to inspect the DB file
  - Open `backend/var/data/app.db` (host) or `/app/var/data/app.db` (container) with any SQLite browser, or use debug endpoints

## Design Notes
- Integer primary keys everywhere for simple, fast joins
- Enums stored as TEXT for SQLite portability
- WAL + busy_timeout improve concurrency; prefer a single backend instance during the hackathon
