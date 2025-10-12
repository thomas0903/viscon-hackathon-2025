"""int-based initial schema

Idempotent: this migration checks for existing tables before creating them.
This makes `upgrade head` safe even if a DB file was created before Alembic
was introduced.

Revision ID: 0001_int_initial
Revises: 
Create Date: 2025-10-10 00:30:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0001_int_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())

    # users
    if "users" not in tables:
        op.create_table(
            "users",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("first_name", sa.String(length=100), nullable=True),
            sa.Column("last_name", sa.String(length=100), nullable=True),
            sa.Column("username", sa.String(length=64), nullable=True),
            sa.Column("email", sa.String(length=255), nullable=True),
            sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("is_association", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("profile_picture_url", sa.String(length=2048), nullable=True),
            sa.Column(
                "visibility_mode",
                sa.Enum("ghost", "friends", "all", name="visibilitymode", native_enum=False),
                nullable=False,
                server_default=sa.text("'all'"),
            ),
            sa.Column(
                "status",
                sa.Enum("active", "disabled", name="accountstatus", native_enum=False),
                nullable=False,
                server_default=sa.text("'active'"),
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("username", name="uq_users_username"),
        )
        op.create_index("ix_users_visibility_mode", "users", ["visibility_mode"], unique=False)
        op.create_index("ix_users_last_seen_at", "users", ["last_seen_at"], unique=False)
        op.create_index("ix_users_is_association", "users", ["is_association"], unique=False)

    # events
    if "events" not in tables:
        op.create_table(
            "events",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("timezone", sa.String(length=64), nullable=True),
            sa.Column("location_name", sa.String(length=255), nullable=True),
            sa.Column("lat", sa.Float(), nullable=True),
            sa.Column("lng", sa.Float(), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("link_url", sa.String(length=2048), nullable=True),
            sa.Column("poster_url", sa.String(length=2048), nullable=True),
            sa.Column("organizer_id", sa.String(length=64), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("category", sa.String(length=64), nullable=True),
            sa.Column("source", sa.String(length=64), nullable=True),
            sa.Column("external_id", sa.String(length=128), nullable=True),
            sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.CheckConstraint("lat IS NULL OR (lat >= -90 AND lat <= 90)", name="valid_lat"),
            sa.CheckConstraint("lng IS NULL OR (lng >= -180 AND lng <= 180)", name="valid_lng"),
            sa.UniqueConstraint("source", "external_id", name="uq_events_source_external_id"),
        )
        op.create_index("ix_events_starts_at", "events", ["starts_at"], unique=False)
        op.create_index("ix_events_is_public", "events", ["is_public"], unique=False)
        op.create_index("ix_events_category", "events", ["category"], unique=False)
        op.create_index("ix_events_organizer_id", "events", ["organizer_id"], unique=False)

    # friendships
    if "friendships" not in tables:
        op.create_table(
            "friendships",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("user_id", sa.String(length=64), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("friend_id", sa.String(length=64), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("requester_id", sa.String(length=64), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column(
                "status",
                sa.Enum("pending", "accepted", "blocked", name="friendshipstatus", native_enum=False),
                nullable=False,
                server_default=sa.text("'pending'"),
            ),
            sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.CheckConstraint("user_id < friend_id", name="friend_ordering"),
            sa.CheckConstraint("requester_id = user_id OR requester_id = friend_id", name="valid_requester"),
            sa.UniqueConstraint("user_id", "friend_id", name="uq_friendships_pair"),
        )
        op.create_index("ix_friendships_user_id", "friendships", ["user_id"], unique=False)
        op.create_index("ix_friendships_friend_id", "friendships", ["friend_id"], unique=False)

    # event_attendance
    if "event_attendance" not in tables:
        op.create_table(
            "event_attendance",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("user_id", sa.String(length=64), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("event_id", sa.String(length=64), sa.ForeignKey("events.id", ondelete="CASCADE"), nullable=False),
            sa.Column(
                "rsvp_status",
                sa.Enum("going", "interested", "declined", name="rsvpstatus", native_enum=False),
                nullable=False,
            ),
            sa.Column(
                "visibility_override",
                sa.Enum("ghost", "friends", "all", name="visibilitymode", native_enum=False),
                nullable=True,
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("checked_in_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("user_id", "event_id", name="uq_event_attendance_user_event"),
        )
        op.create_index("ix_event_attendance_event_status", "event_attendance", ["event_id", "rsvp_status"], unique=False)
        op.create_index("ix_event_attendance_user_id", "event_attendance", ["user_id"], unique=False)

    # event_tags
    if "event_tags" not in tables:
        op.create_table(
            "event_tags",
            sa.Column("event_id", sa.String(length=64), sa.ForeignKey("events.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("tag", sa.String(length=64), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_event_tags_tag", "event_tags", ["tag"], unique=False)
        op.create_index("ix_event_tags_event_id", "event_tags", ["event_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_event_tags_event_id", table_name="event_tags")
    op.drop_index("ix_event_tags_tag", table_name="event_tags")
    op.drop_table("event_tags")

    op.drop_index("ix_event_attendance_user_id", table_name="event_attendance")
    op.drop_index("ix_event_attendance_event_status", table_name="event_attendance")
    op.drop_table("event_attendance")

    op.drop_index("ix_friendships_friend_id", table_name="friendships")
    op.drop_index("ix_friendships_user_id", table_name="friendships")
    op.drop_table("friendships")

    op.drop_index("ix_events_organizer_id", table_name="events")
    op.drop_index("ix_events_category", table_name="events")
    op.drop_index("ix_events_is_public", table_name="events")
    op.drop_index("ix_events_starts_at", table_name="events")
    op.drop_table("events")

    op.drop_index("ix_users_is_association", table_name="users")
    op.drop_index("ix_users_last_seen_at", table_name="users")
    op.drop_index("ix_users_visibility_mode", table_name="users")
    op.drop_table("users")
