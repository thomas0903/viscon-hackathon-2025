from __future__ import annotations

"""Query helpers (repositories) for common read paths.

Keep these small and composable; they return SQLAlchemy models which you can
serialize in your FastAPI routes.
"""
import uuid
from typing import Optional, Sequence

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Event, EventAttendance, Friendship, FriendshipStatus, RSVPStatus, User, VisibilityMode


async def list_events(
    session: AsyncSession,
    *,
    limit: int = 50,
    offset: int = 0,
    is_public: Optional[bool] = None,
    category: Optional[str] = None,
) -> Sequence[Event]:
    """Return upcoming events with simple filters and pagination."""
    q: Select = select(Event).order_by(Event.starts_at.asc().nulls_last())
    if is_public is not None:
        q = q.where(Event.is_public == is_public)
    if category:
        q = q.where(Event.category == category)
    q = q.limit(limit).offset(offset)
    res = await session.execute(q)
    return res.scalars().all()


async def get_user_by_id(session: AsyncSession, user_id: str) -> Optional[User]:
    """Return a user by integer primary key."""
    res = await session.execute(select(User).where(User.id == user_id))
    return res.scalar_one_or_none()


async def list_friends_for_user(session: AsyncSession, user_id: str) -> Sequence[User]:
    """Return all accepted friends for the user (undirected friendships).

    Friendships are stored with ordered pairs (user_id < friend_id).
    """
    a = select(Friendship.friend_id.label("other")).where(
        and_(Friendship.user_id == user_id, Friendship.status == FriendshipStatus.accepted)
    )
    b = select(Friendship.user_id.label("other")).where(
        and_(Friendship.friend_id == user_id, Friendship.status == FriendshipStatus.accepted)
    )
    union_sub = a.union_all(b).subquery("friends_union")
    q = select(User).join(union_sub, User.id == union_sub.c.other)
    res = await session.execute(q)
    return res.scalars().all()

async def add_friendship(session: AsyncSession, user_id: str, friend_id: str) -> Friendship:
    """Create a friendship request from user_id to friend_id."""
    if user_id == friend_id:
        raise ValueError("Cannot befriend oneself")
    uid, fid = (user_id, friend_id) if user_id < friend_id else (friend_id, user_id)
    existing = await session.execute(
        select(Friendship).where(and_(Friendship.user_id == uid, Friendship.friend_id == fid))
    )
    if existing.scalar_one_or_none():
        raise ValueError("Friendship already exists")
    friendship = Friendship(id=f"{uid}|{fid}", user_id=uid, friend_id=fid, requester_id=user_id, status=FriendshipStatus.accepted)
    session.add(friendship)
    await session.commit()
    await session.refresh(friendship)
    return friendship

async def remove_friendship(session: AsyncSession, user_id: str, friend_id: str) -> None:
    """Remove a friendship between user_id and friend_id."""
    if user_id == friend_id:
        raise ValueError("Cannot unfriend oneself")
    existing = await session.execute(
        select(Friendship).where(
            or_(
                and_(Friendship.user_id == user_id, Friendship.friend_id == friend_id),
                and_(Friendship.user_id == friend_id, Friendship.friend_id == user_id),
            )
        )
    )
    friendships = existing.scalars().all()
    if not friendships:
        raise ValueError("Friendship does not exist")
    for friendship in friendships:
        await session.delete(friendship)
    await session.commit()
    return

async def get_events(session: AsyncSession) -> Sequence[Event]:
    """Return all events ordered by start time."""
    res = await session.execute(
        select(Event)
        .order_by(Event.starts_at.asc())
    )
    return res.scalars().all()


async def list_registered_events(
    session: AsyncSession,
    user_id: str,
    *,
    rsvp: RSVPStatus | None = None,
) -> Sequence[Event]:
    """Return events the user has registered for (has an EventAttendance row).

    If rsvp is provided, filter by RSVP status; otherwise include any status.
    Results are ordered by starts_at ascending (upcoming first; nulls last).
    """
    stmt: Select = (
        select(Event)
        .join(EventAttendance, EventAttendance.event_id == Event.id)
        .where(EventAttendance.user_id == user_id)
        .order_by(Event.starts_at.asc().nulls_last())
    )
    if rsvp is not None:
        stmt = stmt.where(EventAttendance.rsvp_status == rsvp)
    res = await session.execute(stmt)
    return res.scalars().all()

async def list_friends_for_event(
    session: AsyncSession,
    user_id: str,
    event_id: str,
    *,
    rsvp: Optional[RSVPStatus] = None,
) -> Sequence[User]:
    """Return the calling user's friends who are attending a specific event.

    Friendships are undirected; check both (user_id -> friend_id) and (friend_id -> user_id).
    """
    a = select(Friendship.friend_id.label("friend")).where(
        and_(Friendship.user_id == user_id, Friendship.status == FriendshipStatus.accepted)
    )
    b = select(Friendship.user_id.label("friend")).where(
        and_(Friendship.friend_id == user_id, Friendship.status == FriendshipStatus.accepted)
    )
    friends_union = a.union_all(b).subquery("friends_union_for_event")

    q = (
        select(User)
        .join(EventAttendance, EventAttendance.user_id == User.id)
        .join(friends_union, friends_union.c.friend == User.id)
        .where(
            and_(
                EventAttendance.event_id == event_id,
                User.visibility_mode.in_([VisibilityMode.friends, VisibilityMode.all]),
            )
        )
    )
    if rsvp is not None:
        q = q.where(EventAttendance.rsvp_status == rsvp)

    res = await session.execute(q)
    return res.scalars().all()


async def count_attendees(session: AsyncSession, event_id: str) -> int:
    """Return total number of attendance rows for an event."""
    res = await session.execute(
        select(func.count()).select_from(EventAttendance).where(EventAttendance.event_id == event_id)
    )
    return int(res.scalar_one())


async def list_attendees_for_event(
    session: AsyncSession,
    event_id: str,
    rsvp: Optional[RSVPStatus] = None,
) -> Sequence[User]:
    """Return all users attending an event, optionally filtered by RSVP status."""
    q: Select = (
        select(User)
        .join(EventAttendance, EventAttendance.user_id == User.id)
        .where(EventAttendance.event_id == event_id)
        .order_by(User.id.asc())
    )
    if rsvp is not None:
        q = q.where(EventAttendance.rsvp_status == rsvp)
    res = await session.execute(q)
    return res.scalars().all()

async def event_sign_up(session: AsyncSession, user_id: str, event_id: str) -> None:
    """Sign up a user for an event."""
    existing = await session.execute(
        select(EventAttendance).where(
            and_(EventAttendance.user_id == user_id, EventAttendance.event_id == event_id)
        )
    )
    if existing.scalar_one_or_none():
        raise ValueError("User already signed up for event")
    attendance = EventAttendance(
        id=str(uuid.uuid4()), user_id=user_id, event_id=event_id, rsvp_status=RSVPStatus.going
    )
    session.add(attendance)
    await session.commit()
    await session.refresh(attendance)
    return

async def event_sign_out(session: AsyncSession, user_id: str, event_id: str) -> None:
    """Remove a user's attendance from an event."""
    existing = await session.execute(
        select(EventAttendance).where(
            and_(EventAttendance.user_id == user_id, EventAttendance.event_id == event_id)
        )
    )
    attendance = existing.scalar_one_or_none()
    if not attendance:
        raise ValueError("User is not signed up for event")
    await session.delete(attendance)
    await session.commit()
    return


async def search_users(
    session: AsyncSession,
    query: str,
    *,
    limit: int = 20,
    offset: int = 0,
) -> Sequence[User]:
    """Simple user search by first/last name or username (case-insensitive)."""
    q = (query or "").strip()
    if not q:
        return []
    pattern = f"%{q.lower()}%"
    stmt: Select = (
        select(User)
        .where(
            or_(
                func.lower(User.first_name).like(pattern),
                func.lower(User.last_name).like(pattern),
                func.lower(User.username).like(pattern),
            )
        )
        .order_by(User.id.asc())
        .limit(limit)
        .offset(offset)
    )
    res = await session.execute(stmt)
    return res.scalars().all()
