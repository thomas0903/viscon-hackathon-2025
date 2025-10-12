import { useEffect, useState } from "react";
import type React from "react";
import { api } from "../apiClient";
import { setCurrentUser as storeSetUser } from "../state/currentUser";
import type { BackendUser } from "../apiClient";
import "./Profile.css";
import ProfileOverview from "../components/ProfileOverview";

type VisibilityMode = 'all' | 'friends' | 'ghost';

const Profile: React.FC = () => {
  const [user, setUser] = useState<BackendUser | null>(null);
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [visibilityMode, setVisibilityMode] = useState<VisibilityMode>('all');
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState({ friends: 0, eventsAttended: 0 });

  useEffect(() => {
    Promise.all([api.getUser(), api.getUserStats()])
      .then(([fetchedUser, statsResp]) => {
        setUser(fetchedUser);
        setFirstName(fetchedUser.first_name || "");
        setLastName(fetchedUser.last_name || "");
        setVisibilityMode((fetchedUser.visibility_mode as VisibilityMode) || 'all');
        setStats({ friends: statsResp.friends_count, eventsAttended: statsResp.events_attended_count });
        setLoading(false);
      })
      .catch((err) => {
        console.error('Failed to load profile data:', err);
        setLoading(false);
      });
  }, []);

  const handleSave = async () => {
    try {
      const updated = await api.updateUserProfile({
        first_name: firstName || null,
        last_name: lastName || null,
        visibility_mode: visibilityMode,
      });
      setUser(updated);
      storeSetUser(updated);
      alert("Settings saved");
    } catch (err) {
      console.error('Failed to save settings:', err);
      alert("Failed to save settings");
    }
  };


  if (loading) {
    return <div style={{ padding: 16 }}>Loading settings…</div>;
  }

  if (!user) {
    return <div style={{ padding: 16 }}>User not found.</div>;
  }

  return (
    <div className="profile-root">
      <ProfileOverview
        user={user}
        stats={stats}
        coverImageSrc="/res/view-3d-cool-modern-bird.jpg"
        editable
        onUserUpdate={(u) => setUser(u)}
      >
        <div className="profile-form">
          <h3 className="profile-section-title">Settings</h3>
          <label className="profile-label">
            <span>First name</span>
            <input
              value={firstName}
              onChange={(e) => setFirstName(e.target.value)}
              placeholder="First name"
              className="profile-input"
            />
          </label>
          <label className="profile-label">
            <span>Last name</span>
            <input
              value={lastName}
              onChange={(e) => setLastName(e.target.value)}
              placeholder="Last name"
              className="profile-input"
            />
          </label>
          <label className="profile-label">
            <span>Visibility mode</span>
            <select
              value={visibilityMode}
              onChange={(e) => setVisibilityMode(e.target.value as VisibilityMode)}
              className="profile-input"
            >
              <option value="all">All</option>
              <option value="friends">Friends</option>
              <option value="ghost">Ghost</option>
            </select>
          </label>
          <div className="profile-small-link-row">
            <a className="profile-small-link" href="/profile/blocked">Manage blocked users</a>
          </div>
          <button
            onClick={handleSave}
            className="profile-save-btn center-btn"
          >
            Save changes
          </button>
        </div>
      </ProfileOverview>
    </div>
  );
};

export default Profile;
