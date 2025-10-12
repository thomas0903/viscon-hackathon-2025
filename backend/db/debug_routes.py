from __future__ import annotations

"""Optional debug endpoints to sanity-check DB queries.

Enable by setting ENABLE_DB_DEBUG_ROUTES=true and starting the backend.
Do not expose these in production; they are for local inspection only.
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from .deps import get_async_session
from .models import RSVPStatus, EventTag
from .repositories import (
    count_attendees,
    get_user_by_id,
    list_attendees_for_event,
    list_events,
    list_friends_for_user,
)


router = APIRouter(prefix="/api/debug", tags=["debug-db"])


@router.get("/events")
async def debug_list_events(
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    is_public: Optional[bool] = None,
    category: Optional[str] = None,
    session: AsyncSession = Depends(get_async_session),
) -> List[Dict[str, Any]]:
    rows = await list_events(session, limit=limit, offset=offset, is_public=is_public, category=category)
    event_ids = [r.id for r in rows]

    tags_map: Dict[str, List[str]] = {eid: [] for eid in event_ids}
    if event_ids:
        res = await session.execute(select(EventTag).where(EventTag.event_id.in_(event_ids)))
        for tag in res.scalars().all():
            tags_map.setdefault(tag.event_id, []).append(tag.tag)

    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append({
            "id": r.id,
            "name": r.name,
            "starts_at": r.starts_at,
            "ends_at": r.ends_at,
            "timezone": r.timezone,
            "location_name": r.location_name,
            "lat": r.lat,
            "lng": r.lng,
            "description": r.description,
            "link_url": r.link_url,
            "poster_url": r.poster_url,
            "organizer_id": r.organizer_id,
            "category": r.category,
            "source": r.source,
            "external_id": r.external_id,
            "is_public": r.is_public,
            "created_at": r.created_at,
            "updated_at": r.updated_at,
            "tags": tags_map.get(r.id, []),
        })
    return out


@router.get("/users/{user_id}")
async def debug_get_user(user_id: str, session: AsyncSession = Depends(get_async_session)) -> Dict[str, Any] | Dict[str, str]:
    u = await get_user_by_id(session, user_id)
    if not u:
        return {"error": "not found"}
    return {
        "id": u.id,
        "first_name": u.first_name,
        "last_name": u.last_name,
        "username": u.username,
        "visibility_mode": u.visibility_mode,
        "is_admin": bool(u.is_admin),
        "is_association": bool(u.is_association),
    }


@router.get("/friends/{user_id}")
async def debug_list_friends(user_id: str, session: AsyncSession = Depends(get_async_session)) -> List[Dict[str, Any]]:
    rows = await list_friends_for_user(session, user_id)
    return [
        {
            "id": r.id,
            "username": r.username,
            "visibility_mode": r.visibility_mode,
        }
        for r in rows
    ]


@router.get("/events/{event_id}/attendees")
async def debug_list_attendees(
    event_id: str,
    rsvp: Optional[RSVPStatus] = None,
    session: AsyncSession = Depends(get_async_session),
) -> Dict[str, Any]:
    users = await list_attendees_for_event(session, event_id, rsvp=rsvp)
    total = await count_attendees(session, event_id)
    return {
        "event_id": event_id,
        "total": total,
        "users": [{"id": u.id, "username": u.username} for u in users],
    }
