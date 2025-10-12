export class ApiError extends Error {
  status: number;
  detail?: unknown;
  constructor(status: number, message: string, detail?: unknown) {
    super(`${status} ${message}`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

type HttpMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

const BASE_URL = import.meta.env?.VITE_API_BASE_URL ?? ""; // same-origin via Vite proxy by default

async function request<T>(endpoint: string, method: HttpMethod = "GET", body?: unknown | FormData): Promise<T> {
  const headers = new Headers({ "Accept": "application/json" });
  const init: RequestInit = { method, headers };

  if (body !== undefined) {
    if (body instanceof FormData) {
      init.body = body; // Let the browser set multipart/form-data with boundary
    } else {
      headers.set("Content-Type", "application/json");
      init.body = JSON.stringify(body);
    }
  }

  const res = await fetch(`${BASE_URL}${endpoint}`, init);
  const isJson = (res.headers.get("content-type") || "").includes("application/json");
  let data: unknown = undefined;
  try {
    data = isJson && res.status !== 204 ? await res.json() : undefined;
  } catch (_) {
    // ignore JSON parse errors for non-JSON responses
  }
  if (!res.ok) {
    const message = (data && typeof data === "object" && (data as any).detail) || res.statusText || "Request failed";
    throw new ApiError(res.status, String(message), data);
  }
  return data as T;
}

// Backend-aligned types (from backend/models.py)
export type VisibilityMode = "ghost" | "friends" | "all";
export type AccountStatus = "active" | "disabled";

export interface BackendUser {
  id: string;
  first_name: string | null;
  last_name: string | null;
  username: string | null;
  email: string | null;
  is_admin: boolean;
  is_association: boolean;
  profile_picture_url: string | null;
  visibility_mode: VisibilityMode;
  status: AccountStatus;
  created_at: string; // ISO datetime
  updated_at: string; // ISO datetime
  last_seen_at: string | null; // ISO datetime
}

export interface BackendEvent {
  id: string;
  name: string;
  starts_at: string | null;
  ends_at: string | null;
  timezone: string | null;
  location_name: string | null;
  lat: number | null;
  lng: number | null;
  description: string | null;
  link_url: string | null;
  poster_url: string | null;
  organizer_id: string | null;
  category: string | null;
  source: string | null;
  external_id: string | null;
  is_public: boolean;
  created_at: string;
  updated_at: string;
  friends?: BackendUser[];
  attendees_count?: number;
}

export type FriendshipLifecycle = "pending" | "accepted" | "blocked";

export interface BackendFriendship {
  id: string;
  user_id: string;
  friend_id: string;
  requester_id: string;
  status: FriendshipLifecycle;
  requested_at: string;
  accepted_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface FriendshipStatusResponse {
  is_friend: boolean;
  common_friends: number;
}

export interface UserStatsResponse {
  friends_count: number;
  events_attended_count: number;
}

// API calls aligned to backend/app.py
export function getUser(): Promise<BackendUser> {
  return request(`/api/user`, "GET");
}

export function getUserFriends(): Promise<BackendUser[]> {
  return request(`/api/friends`, "GET");
}

export function addFriend(friendId: number | string): Promise<BackendFriendship> {
  return request(`/api/friends/${friendId}`, "PUT");
}

export function removeFriend(friendId: number | string): Promise<void> {
  return request(`/api/friends/${friendId}`, "DELETE");
}

export function getFriendshipStatus(currentUserId: number | string, targetUserId: number | string): Promise<FriendshipStatusResponse> {
  return request(`/api/friendship/${currentUserId}/${targetUserId}`, "GET");
}

export function getUserEvents(): Promise<BackendEvent[]> {
  return request(`/api/events`, "GET");
}

// Events attended by a specific user (past events). Backend route exists.
export function getAttendedEvents(userId: string | number): Promise<BackendEvent[]> {
  return request(`/api/events/${userId}/attended`, "GET");
}

// Registered events for the current user (any time)
export function getRegisteredEvents(): Promise<BackendEvent[]> {
  return request(`/api/events/registered`, "GET");
}

export function getUserStats(): Promise<UserStatsResponse> {
  return request(`/api/user/stats`, "GET");
}

// Blocked users API
export function getBlockedUsers(): Promise<BackendUser[]> {
  return request(`/api/blocked`, "GET");
}

export function blockUser(targetId: string | number): Promise<{ ok: boolean; user: BackendUser | null }> {
  return request(`/api/blocked/${targetId}`, "PUT");
}

export function unblockUser(targetId: string | number): Promise<void> {
  return request(`/api/blocked/${targetId}`, "DELETE");
}

// Event attendance
export function joinEvent(eventId: string | number): Promise<void> {
  return request(`/api/events/${eventId}/attendees`, "POST");
}

export function leaveEvent(eventId: string | number): Promise<void> {
  return request(`/api/events/${eventId}/attendees`, "DELETE");
}

// Current user's attendance for a specific event
export function getMyAttendance(eventId: string | number): Promise<{ attending: boolean; rsvp_status: "going" | "interested" | "declined" | null }>{
  return request(`/api/events/${encodeURIComponent(String(eventId))}/attendees/me`, "GET");
}

// Uploads API
export async function uploadImage(
  file: File,
  scope: "user" | "event",
  ownerId: number | string,
): Promise<{ url: string; size: number; content_type: string }> {
  const form = new FormData();
  form.append("file", file);
  const params = new URLSearchParams({ scope, owner_id: String(ownerId) });
  return request(`/api/uploads?${params.toString()}`, "POST", form);
}

// Search users
export function searchUsers(query: string, limit = 20, offset = 0): Promise<BackendUser[]> {
  const params = new URLSearchParams({ q: query, limit: String(limit), offset: String(offset) });
  return request(`/api/users/search?${params.toString()}`, "GET");
}

// Optional grouped export for convenience
export const api = {
  getUser,
  getUserFriends,
  addFriend,
  removeFriend,
  getFriendshipStatus,
  getUserEvents,
  getAttendedEvents,
  getRegisteredEvents,
  getUserStats,
  getBlockedUsers,
  blockUser,
  unblockUser,
  joinEvent,
  leaveEvent,
  uploadImage,
  searchUsers,
  setUserProfilePicture,
  updateUserProfile,
};

// User profile updates
export function setUserProfilePicture(url: string): Promise<BackendUser> {
  return request(`/api/user/profile-picture`, "PATCH", { url });
}

export function updateUserProfile(
  data: Partial<Pick<BackendUser, "first_name" | "last_name" | "visibility_mode">>
): Promise<BackendUser> {
  return request(`/api/user`, "PATCH", data);
}
