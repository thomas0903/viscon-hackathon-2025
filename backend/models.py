from pydantic import BaseModel, ConfigDict
from typing import Sequence
from datetime import datetime
from typing import Optional
from db.models import AccountStatus, VisibilityMode, FriendshipStatus  # reuse the enums

class User(BaseModel):
    id: str | int
    first_name: Optional[str]
    last_name: Optional[str]
    username: Optional[str]
    email: Optional[str]
    is_admin: bool
    is_association: bool
    profile_picture_url: Optional[str]
    visibility_mode: VisibilityMode
    status: AccountStatus
    created_at: datetime
    updated_at: datetime
    last_seen_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)

class Event(BaseModel):
    id: str | int
    name: str
    starts_at: Optional[datetime]
    ends_at: Optional[datetime]
    timezone: Optional[str]
    location_name: Optional[str]
    lat: Optional[float]
    lng: Optional[float]
    description: Optional[str]
    link_url: Optional[str]
    poster_url: Optional[str]
    organizer_id: Optional[str]
    category: Optional[str]
    source: Optional[str]
    external_id: Optional[str]
    is_public: bool
    created_at: datetime
    updated_at: datetime

    friends: Optional[Sequence[User]] = None
    attendees_count: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)

class Friendship(BaseModel):
    id: str
    user_id: str
    friend_id: str
    requester_id: str
    status: FriendshipStatus
    requested_at: datetime
    accepted_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class FriendshipStatus(BaseModel):
    is_friend: bool
    common_friends: int

class AuthenticatedUser(BaseModel):
    id: str
    name: str
