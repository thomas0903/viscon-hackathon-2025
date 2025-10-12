import { useEffect, useState } from "react";
import type React from "react";
import { useParams } from "react-router-dom";
import { getUser, getFriendshipStatus, addFriend, type BackendUser } from "../apiClient";
import ProfileOverview from "../components/ProfileOverview";
import "./Profile.css";

const UserProfile: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const [user, setUser] = useState<BackendUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [stats, setStats] = useState<{ friends: number; eventsAttended: number }>({ friends: 0, eventsAttended: 0 });
  const [isFriend, setIsFriend] = useState<boolean>(false);
  const [adding, setAdding] = useState<boolean>(false);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);

    if (!id) {
      setError("No user id specified");
      setLoading(false);
      return () => { active = false; };
    }

    // Mock: allow viewing a sample profile at /profile/test without backend
    if (id === "test") {
      const nowIso = new Date().toISOString();
      const mockUser: BackendUser = {
        id: id,
        first_name: "Test",
        last_name: "User",
        username: null,
        email: null,
        is_admin: false,
        is_association: false,
        profile_picture_url: "/res/Portrait_Placeholder.png",
        visibility_mode: "all",
        status: "active",
        created_at: nowIso,
        updated_at: nowIso,
        last_seen_at: null,
      };
      setUser(mockUser);
      setLoading(false);
      return () => { active = false; };
    }

    getUser()
      .then((u) => {
        if (!active) return;
        setUser(u);
      })
      .catch((e) => {
        if (!active) return;
        setError(e?.message || "Failed to load user");
      })
      .finally(() => {
        if (!active) return;
        setLoading(false);
      });

    // Fetch friendship status and common friends count from backend
    const currentUserId = 1; // mock current user id
    getFriendshipStatus(currentUserId, id)
      .then((res) => {
        if (!active) return;
        setIsFriend(Boolean(res.is_friend));
        setStats((s) => ({ ...s, friends: res.common_friends }));
      })
      .catch(() => {
        /* ignore for now */
      });

    // Events attended isn't wired yet; keep 0 or mock later

    return () => {
      active = false;
    };
  }, [id]);

  if (loading) {
    return <div style={{ padding: 16 }}>Loading profile…</div>;
  }

  if (error) {
    return <div style={{ padding: 16, color: "#b91c1c" }}>Error: {error}</div>;
  }

  if (!user) {
    return <div style={{ padding: 16 }}>User not found.</div>;
  }

  const handleAddFriend = async () => {
    if (!user || adding) return;
    try {
      setAdding(true);
      await addFriend(user.id);
      setIsFriend(true);
      setStats((s) => ({ ...s, friends: s.friends + 1 }));
    } finally {
      setAdding(false);
    }
  };

  return (
    <div className="profile-root">
      <ProfileOverview user={user} stats={stats} statLabels={{ friends: "Common friends", eventsAttended: "Events attended" }}>
        <div style={{ display: "flex", justifyContent: "center", marginTop: 8 }}>
          {isFriend ? (
            <button className="profile-link-btn" disabled>
              Already friends
            </button>
          ) : (
            <button className="profile-save-btn" onClick={handleAddFriend} disabled={adding}>
              {adding ? "Adding…" : "Add friend"}
            </button>
          )}
        </div>
      </ProfileOverview>
    </div>
  );
};

export default UserProfile;
