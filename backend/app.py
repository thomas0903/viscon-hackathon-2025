from os import getenv
from models import User, Event, Friendship, FriendshipStatus

import uvicorn

from fastapi import FastAPI, HTTPException, status, Depends
from pydantic import BaseModel
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from fastapi.middleware.cors import CORSMiddleware

from sqlalchemy.ext.asyncio import AsyncSession
from db.deps import get_async_session, get_or_create_current_user

from db.repositories import list_events, get_user_by_id, list_friends_for_user, add_friendship, remove_friendship, get_events, list_friends_for_event, count_attendees, search_users, event_sign_up, event_sign_out, list_registered_events

from db.models import (
    Event as ORMEvent,
    EventAttendance,
    VisibilityMode as DbVisibilityMode,
    Friendship as ORMFriendship,
    FriendshipStatus as ORMFriendshipStatus,
    User as ORMUser,
)
from sqlalchemy import select, func, and_, or_

ENABLE_DB_DEBUG_ROUTES = getenv("ENABLE_DB_DEBUG_ROUTES", "false").lower() == "true"

app = FastAPI(docs_url="/api/docs", openapi_url="/api/openapi.json")
# Avoid 307 redirects between `/path` and `/path/` to prevent mixed-content issues behind proxies
try:
    app.router.redirect_slashes = False
except Exception:
    pass

# Add CORS middleware to allow requests from frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For development; replace with frontend URL for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def compute_friendship_status(current_user_id: str, target_user_id: str) -> FriendshipStatus:
    # Mock computation: returns non-zero common friends for demonstration
    is_friend = str(current_user_id) == str(target_user_id)
    common = 5 if not is_friend else 0
    return FriendshipStatus(is_friend=is_friend, common_friends=common)
  
@app.get("/api/user", response_model=User)
@app.get("/api/user/", response_model=User)
async def read_user(current = Depends(get_or_create_current_user), session: AsyncSession = Depends(get_async_session)):
    orm_user = await get_user_by_id(session, current.id)
    if orm_user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return User.model_validate(orm_user)

@app.get("/api/friends", response_model=list[User])
@app.get("/api/friends/", response_model=list[User])
async def get_friends(current = Depends(get_or_create_current_user), session: AsyncSession = Depends(get_async_session)):
    orm_friends = await list_friends_for_user(session, current.id)
    return [User.model_validate(orm_friend) for orm_friend in orm_friends]

@app.put("/api/friends/{friend_id}", response_model=Friendship)
@app.put("/api/friends/{friend_id}/", response_model=Friendship)
async def add_friend(friend_id: str, current = Depends(get_or_create_current_user), session: AsyncSession = Depends(get_async_session)):
    try :
        orm_friendship = await add_friendship(session, current.id, friend_id)
    except ValueError:
        raise HTTPException(status_code=409, detail="Friendship already exists")
    return Friendship.model_validate(orm_friendship)

@app.delete("/api/friends/{friend_id}")
@app.delete("/api/friends/{friend_id}/")
async def remove_friend(friend_id: str, current = Depends(get_or_create_current_user), session: AsyncSession = Depends(get_async_session)):
    await remove_friendship(session, current.id, friend_id)
    return

@app.get("/api/events", response_model=list[Event])
@app.get("/api/events/", response_model=list[Event])
async def list_events(current = Depends(get_or_create_current_user), session: AsyncSession = Depends(get_async_session)):
    res = []
    orm_events = await get_events(session)
    for orm_event in orm_events:
        event = Event.model_validate(orm_event)
        list_friend = await list_friends_for_event(session, current.id, orm_event.id)
        event.friends = [User.model_validate(orm_friend) for orm_friend in list_friend]
        attendes = await count_attendees(session, orm_event.id)
        event.attendees_count = attendes
        res.append(event)

    return res

@app.get("/api/events/registered", response_model=list[Event])
async def list_registered(current = Depends(get_or_create_current_user), session: AsyncSession = Depends(get_async_session)):
    res: list[Event] = []
    orm_events = await list_registered_events(session, current.id)
    for oe in orm_events:
        ev = Event.model_validate(oe)
        friends = await list_friends_for_event(session, current.id, oe.id)
        ev.friends = [User.model_validate(u) for u in friends]
        ev.attendees_count = await count_attendees(session, oe.id)
        res.append(ev)
    return res

@app.get("/api/events/{user_id}/attended", response_model=list[Event])
async def get_attended_events(user_id: str, session: AsyncSession = Depends(get_async_session)) -> list[Event]:
    res = await session.execute(
        select(ORMEvent)
        .join(EventAttendance, ORMEvent.id == EventAttendance.event_id)
        .where(
            and_(
                EventAttendance.user_id == user_id,
                ORMEvent.starts_at.is_not(None),
                ORMEvent.starts_at < func.now(),
            )
        )
        .order_by(ORMEvent.starts_at.desc())
    )
    return [Event.model_validate(evt) for evt in res.scalars().all()]

@app.get("/api/friendship/{current_user_id}/{target_user_id}", response_model=FriendshipStatus, status_code=status.HTTP_200_OK)
def friendship_status(current_user_id: str, target_user_id: str):
    return compute_friendship_status(current_user_id, target_user_id)

@app.get("/api/users/search", response_model=list[User])
async def search_users_route(q: str, limit: int = 20, offset: int = 0, session: AsyncSession = Depends(get_async_session)):
    orm_users = await search_users(session, q, limit=limit, offset=offset)
    return [User.model_validate(u) for u in orm_users]

async def _resolve_event_id(session: AsyncSession, event_id: str) -> str:
    # Accept either canonical id ("vis.ethz.ch:934") or external_id only ("934")
    res = await session.execute(
        select(ORMEvent.id).where(or_(ORMEvent.id == event_id, ORMEvent.external_id == event_id))
    )
    found = res.scalar_one_or_none()
    if not found:
        raise HTTPException(status_code=404, detail="Event not found")
    return str(found)


@app.post("/api/events/{event_id}/attendees", status_code=status.HTTP_204_NO_CONTENT)
async def sign_up_event(event_id : str, current = Depends(get_or_create_current_user), session: AsyncSession = Depends(get_async_session)):
    canonical_id = await _resolve_event_id(session, event_id)
    try:
        await event_sign_up(session, current.id, canonical_id)
    except ValueError:
        # Already signed up; treat as idempotent success
        pass
    return

@app.delete( "/api/events/{event_id}/attendees", status_code=status.HTTP_204_NO_CONTENT,)
async def leave_event(event_id: str,current = Depends(get_or_create_current_user), session: AsyncSession = Depends(get_async_session),):
    canonical_id = await _resolve_event_id(session, event_id)
    try:
        await event_sign_out(session, current.id, canonical_id)
    except ValueError:
        # Not signed up; treat as idempotent success
        pass
    return

# Query current user's attendance for a given event (simple boolean + status)
@app.get("/api/events/{event_id}/attendees/me")
async def my_attendance(event_id: str, current = Depends(get_or_create_current_user), session: AsyncSession = Depends(get_async_session)):
    canonical_id = await _resolve_event_id(session, event_id)
    res = await session.execute(
        select(EventAttendance).where(
            and_(EventAttendance.user_id == current.id, EventAttendance.event_id == canonical_id)
        )
    )
    row = res.scalar_one_or_none()
    return {
        "attending": bool(row is not None),
        "rsvp_status": (row.rsvp_status.value if row and getattr(row, "rsvp_status", None) is not None else None),
    }

class _ProfilePictureBody(BaseModel):
    url: str


@app.patch("/api/user/profile-picture", response_model=User)
@app.patch("/api/user/profile-picture/", response_model=User)
async def update_profile_picture(
    body: _ProfilePictureBody,
    current = Depends(get_or_create_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    orm_user = await get_user_by_id(session, current.id)
    if orm_user is None:
        raise HTTPException(status_code=404, detail="User not found")
    orm_user.profile_picture_url = body.url
    await session.commit()
    await session.refresh(orm_user)
    return User.model_validate(orm_user)


class _UserStats(BaseModel):
    friends_count: int
    events_attended_count: int


@app.get("/api/user/stats", response_model=_UserStats)
@app.get("/api/user/stats/", response_model=_UserStats)
async def get_user_stats(current = Depends(get_or_create_current_user), session: AsyncSession = Depends(get_async_session)):
    # Friends count via repository helper
    friends = await list_friends_for_user(session, current.id)
    friends_count = len(friends)

    # Events attended count via direct COUNT on EventAttendance
    res = await session.execute(
        select(func.count()).select_from(EventAttendance).where(EventAttendance.user_id == current.id)
    )
    events_attended_count = int(res.scalar_one() or 0)
    return _UserStats(friends_count=friends_count, events_attended_count=events_attended_count)


class _UpdateUserBody(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    visibility_mode: DbVisibilityMode | None = None


@app.patch("/api/user", response_model=User)
@app.patch("/api/user/", response_model=User)
async def update_user(
    body: _UpdateUserBody,
    current = Depends(get_or_create_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    orm_user = await get_user_by_id(session, current.id)
    if orm_user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if body.first_name is not None:
        orm_user.first_name = body.first_name or None
    if body.last_name is not None:
        orm_user.last_name = body.last_name or None
    if body.visibility_mode is not None:
        orm_user.visibility_mode = body.visibility_mode
    await session.commit()
    await session.refresh(orm_user)
    return User.model_validate(orm_user)


# Blocked users API (uses Friendship table with status = blocked)

@app.get("/api/blocked", response_model=list[User])
@app.get("/api/blocked/", response_model=list[User])
async def list_blocked(current = Depends(get_or_create_current_user), session: AsyncSession = Depends(get_async_session)):
    a = select(ORMFriendship.friend_id.label("other")).where(
        and_(ORMFriendship.user_id == current.id, ORMFriendship.status == ORMFriendshipStatus.blocked)
    )
    b = select(ORMFriendship.user_id.label("other")).where(
        and_(ORMFriendship.friend_id == current.id, ORMFriendship.status == ORMFriendshipStatus.blocked)
    )
    union_sub = a.union_all(b).subquery("blocked_union")
    q = select(ORMUser).join(union_sub, ORMUser.id == union_sub.c.other)
    res = await session.execute(q)
    users = res.scalars().all()
    return [User.model_validate(u) for u in users]


class _BlockedActionResponse(BaseModel):
    ok: bool = True
    user: User | None = None


@app.put("/api/blocked/{target_id}", response_model=_BlockedActionResponse)
@app.put("/api/blocked/{target_id}/", response_model=_BlockedActionResponse)
async def block_user(
    target_id: str,
    current = Depends(get_or_create_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    if str(target_id) == str(current.id):
        raise HTTPException(status_code=400, detail="Cannot block oneself")

    # Order the pair: uid < fid (lexicographically for strings)
    uid, fid = (current.id, target_id) if str(current.id) < str(target_id) else (target_id, current.id)

    # Look for an existing row using the ordered pair
    res = await session.execute(
        select(ORMFriendship).where(and_(ORMFriendship.user_id == uid, ORMFriendship.friend_id == fid))
    )
    row = res.scalar_one_or_none()
    if row:
        row.status = ORMFriendshipStatus.blocked
        row.requester_id = current.id
    else:
        row = ORMFriendship(
            id=f"{uid}|{fid}",
            user_id=uid,
            friend_id=fid,
            requester_id=current.id,
            status=ORMFriendshipStatus.blocked,
        )
        session.add(row)

    await session.commit()

    target = await get_user_by_id(session, target_id)
    return _BlockedActionResponse(ok=True, user=User.model_validate(target) if target else None)


@app.delete("/api/blocked/{target_id}")
@app.delete("/api/blocked/{target_id}/")
async def unblock_user(target_id: str, current = Depends(get_or_create_current_user), session: AsyncSession = Depends(get_async_session)):
    uid, fid = (current.id, target_id) if str(current.id) < str(target_id) else (target_id, current.id)
    res = await session.execute(select(ORMFriendship).where(and_(ORMFriendship.user_id == uid, ORMFriendship.friend_id == fid)))
    row = res.scalar_one_or_none()
    if row and row.status == ORMFriendshipStatus.blocked:
        await session.delete(row)
        await session.commit()
    return
  

# Optional: mount debug DB routes if enabled
if ENABLE_DB_DEBUG_ROUTES:
    try:
        # greenlet is required for async DB queries; gracefully skip if missing
        try:
            import greenlet  # noqa: F401
        except Exception:  # pragma: no cover
            raise RuntimeError("Greenlet not installed; debug DB routes disabled.")

        from db.debug_routes import router as debug_db_router

        app.include_router(debug_db_router)
        print("DB debug routes enabled at /api/debug ...")
    except Exception as e:
        print(f"Failed to enable DB debug routes: {e}")

# Ensure upload directory exists before mounting
try:
    Path("var/uploads").mkdir(parents=True, exist_ok=True)
except Exception:
    pass

# Serve uploaded files under /uploads
app.mount("/uploads", StaticFiles(directory="var/uploads"), name="uploads")

# Upload API
try:
    from uploads import router as uploads_router

    app.include_router(uploads_router)
except Exception as e:
    print(f"Failed to include uploads router: {e}")

# Graph API
try:
    from graph_api import router as graph_router

    app.include_router(graph_router)
except Exception as e:
    print(f"Failed to include graph router: {e}")


if __name__ == "__main__":
    print(f"Starting server")
    uvicorn.run(
        "__main__:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )
