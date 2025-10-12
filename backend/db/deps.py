from __future__ import annotations

"""FastAPI dependency helpers for database sessions."""

from typing import AsyncGenerator, Optional
import os
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from .models import User, VisibilityMode

from sqlalchemy.ext.asyncio import AsyncSession

from .base import AsyncSessionLocal


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an AsyncSession; use with Depends(get_async_session)."""
    async with AsyncSessionLocal() as session:
        yield session


async def get_or_create_current_user(
    request: Request,
    session: AsyncSession = Depends(get_async_session),
) -> User:
    """Resolve the current user from proxy headers and upsert into DB.

    - If USE_MOCK_AUTHENTICATION != "false" and headers missing, use dev fallback.
    - User primary key is a string id; we also set username to the same value.
    """
    user_id_hdr: Optional[str] = request.headers.get("X-User-Id")
    full_name: str = (request.headers.get("X-User-Name") or "").strip()

    if not user_id_hdr:
        if os.getenv("USE_MOCK_AUTHENTICATION", "true").lower() != "false":
            user_id_hdr = "dev-user"
            if not full_name:
                full_name = "Dev User"
        else:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing X-User-Id header")

    # Split name into first/last heuristically
    first, last = None, None
    if full_name:
        parts = full_name.split()
        first = parts[0]
        last = " ".join(parts[1:]) if len(parts) > 1 else None

    # Fetch by PK first
    res = await session.execute(select(User).where(User.id == user_id_hdr[:64]))
    orm_user = res.scalar_one_or_none()
    if orm_user:
        return orm_user

    # Create
    new_user = User(
        id=user_id_hdr[:64],
        username=user_id_hdr,
        first_name=first,
        last_name=last,
        visibility_mode=VisibilityMode.all,
        is_admin=False,
        is_association=False,
    )
    session.add(new_user)
    try:
        await session.commit()
        await session.refresh(new_user)
        return new_user
    except IntegrityError:
        # Likely created concurrently in another request; fetch existing and return
        await session.rollback()
        res2 = await session.execute(select(User).where(User.username == user_id_hdr))
        existing = res2.scalar_one_or_none()
        if existing:
            return existing
        # Last resort: try by id
        res3 = await session.execute(select(User).where(User.id == user_id_hdr[:64]))
        existing2 = res3.scalar_one_or_none()
        if existing2:
            return existing2
        # Unexpected; bubble up
        raise
