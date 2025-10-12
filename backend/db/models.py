"""ORM models for the application.

"""
import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class VisibilityMode(str, enum.Enum):
    """Controls who can see a user's attendance."""
    ghost = "ghost"
    friends = "friends"
    all = "all"


class AccountStatus(str, enum.Enum):
    """Logical status for accounts (e.g., disabled by admins)."""
    active = "active"
    disabled = "disabled"


class FriendshipStatus(str, enum.Enum):
    """Lifecycle of a friendship request."""
    pending = "pending"
    accepted = "accepted"
    blocked = "blocked"


class RSVPStatus(str, enum.Enum):
    """User's RSVP state for an event."""
    going = "going"
    interested = "interested"
    declined = "declined"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    first_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str | None] = mapped_column(String(100))
    username: Mapped[str | None] = mapped_column(String(64), unique=True)
    email: Mapped[str | None] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    is_association: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    profile_picture_url: Mapped[str | None] = mapped_column(String(2048))
    visibility_mode: Mapped[VisibilityMode] = mapped_column(
        Enum(VisibilityMode, native_enum=False, validate_strings=True),
        nullable=False,
        server_default=VisibilityMode.all.value,
    )
    status: Mapped[AccountStatus] = mapped_column(
        Enum(AccountStatus, native_enum=False, validate_strings=True),
        nullable=False,
        server_default=AccountStatus.active.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # events organized by this user (nullable organizer on Event)
    organized_events = relationship("Event", back_populates="organizer", cascade="all,delete")

    __table_args__ = (
        Index("ix_users_visibility_mode", "visibility_mode"),
        Index("ix_users_last_seen_at", "last_seen_at"),
        Index("ix_users_is_association", "is_association"),
    )


class Friendship(Base):
    __tablename__ = "friendships"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    friend_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    requester_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[FriendshipStatus] = mapped_column(
        Enum(FriendshipStatus, native_enum=False, validate_strings=True),
        nullable=False,
        server_default=FriendshipStatus.pending.value,
    )
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    user = relationship("User", foreign_keys=[user_id])
    friend = relationship("User", foreign_keys=[friend_id])
    requester = relationship("User", foreign_keys=[requester_id])

    __table_args__ = (
        UniqueConstraint("user_id", "friend_id", name="uq_friendships_pair"),
        CheckConstraint("user_id < friend_id", name="friend_ordering"),
        CheckConstraint("requester_id = user_id OR requester_id = friend_id", name="valid_requester"),
        Index("ix_friendships_user_id", "user_id"),
        Index("ix_friendships_friend_id", "friend_id"),
    )


class Event(Base):
    __tablename__ = "events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    timezone: Mapped[str | None] = mapped_column(String(64))
    location_name: Mapped[str | None] = mapped_column(String(255))
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    description: Mapped[str | None] = mapped_column(Text)
    link_url: Mapped[str | None] = mapped_column(String(2048))
    poster_url: Mapped[str | None] = mapped_column(String(2048))
    organizer_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"))
    category: Mapped[str | None] = mapped_column(String(64))
    source: Mapped[str | None] = mapped_column(String(64))
    external_id: Mapped[str | None] = mapped_column(String(128))
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    organizer = relationship("User", back_populates="organized_events")
    tags = relationship("EventTag", back_populates="event", cascade="all,delete-orphan")

    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_events_source_external_id"),
        Index("ix_events_starts_at", "starts_at"),
        Index("ix_events_is_public", "is_public"),
        Index("ix_events_category", "category"),
        Index("ix_events_organizer_id", "organizer_id"),
        CheckConstraint("lat IS NULL OR (lat >= -90 AND lat <= 90)", name="valid_lat"),
        CheckConstraint("lng IS NULL OR (lng >= -180 AND lng <= 180)", name="valid_lng"),
    )


class EventAttendance(Base):
    __tablename__ = "event_attendance"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    event_id: Mapped[str] = mapped_column(String(64), ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    rsvp_status: Mapped[RSVPStatus] = mapped_column(
        Enum(RSVPStatus, native_enum=False, validate_strings=True), nullable=False
    )
    visibility_override: Mapped[VisibilityMode | None] = mapped_column(
        Enum(VisibilityMode, native_enum=False, validate_strings=True)
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user = relationship("User")
    event = relationship("Event")

    __table_args__ = (
        UniqueConstraint("user_id", "event_id", name="uq_event_attendance_user_event"),
        Index("ix_event_attendance_event_status", "event_id", "rsvp_status"),
        Index("ix_event_attendance_user_id", "user_id"),
    )


class EventTag(Base):
    __tablename__ = "event_tags"

    event_id: Mapped[str] = mapped_column(String(64), ForeignKey("events.id", ondelete="CASCADE"), primary_key=True)
    tag: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    event = relationship("Event", back_populates="tags")

    __table_args__ = (
        Index("ix_event_tags_tag", "tag"),
        Index("ix_event_tags_event_id", "event_id"),
    )
