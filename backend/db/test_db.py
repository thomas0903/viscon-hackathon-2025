from __future__ import annotations

"""Lightweight DB smoke tests used by `make db-test`.

Creates a couple of rows, verifies simple queries, then cleans them up.
"""

import sys
import time
from contextlib import contextmanager

from sqlalchemy import select

from .base import SessionLocal
from .models import Event, EventAttendance, Friendship, FriendshipStatus, RSVPStatus, User, VisibilityMode


class TestFailure(Exception):
    pass


@contextmanager
def session_scope():
    """Provide a transactional scope around a series of operations."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def print_ok(msg: str) -> None:
    print(f"[PASS] {msg}")


def print_fail(msg: str) -> None:
    print(f"[FAIL] {msg}")


def run() -> None:
    suffix = str(int(time.time()))  # unique suffix to avoid conflicts

    try:
        with session_scope() as s:
            # Connectivity
            s.execute(select(1))
            print_ok("Connected to SQLite and executed a simple query")

            # Create two users
            u1 = User(first_name="Test", last_name="UserA", username=f"test_user_a_{suffix}", visibility_mode=VisibilityMode.all)
            u2 = User(first_name="Test", last_name="UserB", username=f"test_user_b_{suffix}", visibility_mode=VisibilityMode.all)
            s.add_all([u1, u2])
            s.flush()  # assign IDs
            assert u1.id and u2.id
            print_ok("Created users with integer IDs")

            # Friendship accepted (ordering enforced by constraint user_id < friend_id)
            a, b = sorted([u1.id, u2.id])
            fr = Friendship(user_id=a, friend_id=b, requester_id=a, status=FriendshipStatus.accepted)
            s.add(fr)
            s.flush()
            print_ok("Created friendship (accepted)")

            # Create an event
            ev = Event(name=f"Test Event {suffix}")
            s.add(ev)
            s.flush()
            assert ev.id
            print_ok("Created event")

            # Mark attendance
            ea = EventAttendance(user_id=u1.id, event_id=ev.id, rsvp_status=RSVPStatus.going)
            s.add(ea)
            s.flush()

            # Query attendees
            attendees = (
                s.execute(
                    select(User).join(EventAttendance, EventAttendance.user_id == User.id).where(
                        EventAttendance.event_id == ev.id
                    )
                )
                .scalars()
                .all()
            )
            assert any(x.id == u1.id for x in attendees)
            print_ok("Attendance recorded and attendees query returns expected user")

            # Cleanup created rows (best-effort)
            for obj in [ea, fr, ev, u1, u2]:
                try:
                    s.delete(obj)
                except Exception:
                    pass
            print_ok("Cleanup completed")

        print("All DB tests passed.")
        sys.exit(0)

    except AssertionError as e:
        print_fail(f"Assertion failed: {e}")
        sys.exit(1)
    except Exception as e:
        print_fail(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    run()
