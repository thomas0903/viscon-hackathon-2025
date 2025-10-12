import { useRef, useState, type ReactNode } from "react";
import type { BackendUser } from "../apiClient";
import { api } from "../apiClient";
import { setCurrentUser as storeSetUser } from "../state/currentUser";
import "../pages/Profile.css";

type ProfileStats = {
  friends: number;
  eventsAttended: number;
};

interface StatLabels {
  friends?: string;
  eventsAttended?: string;
}

interface ProfileOverviewProps {
  user: BackendUser;
  stats?: ProfileStats;
  coverImageSrc?: string;
  children?: ReactNode;
  statLabels?: StatLabels;
  editable?: boolean;
  onUserUpdate?: (user: BackendUser) => void;
}

const DEFAULT_COVER = "/res/view-3d-cool-modern-bird.jpg";
const DEFAULT_AVATAR = "/res/Portrait_Placeholder.png";

const ProfileOverview: React.FC<ProfileOverviewProps> = ({
  user,
  stats,
  coverImageSrc = DEFAULT_COVER,
  children,
  statLabels,
  editable = false,
  onUserUpdate,
}) => {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [uploading, setUploading] = useState(false);

  const handleUploadClick = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      setUploading(true);
      const up = await api.uploadImage(file, "user", user.id);
      const updated = await api.setUserProfilePicture(up.url);
      onUserUpdate?.(updated);
      storeSetUser(updated);
    } catch (err) {
      console.error("Failed to upload avatar:", err);
      alert("Failed to upload image. Please try a different file.");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };
  return (
    <>
      <div className="profile-hero">
        <img src={coverImageSrc} alt="Cover" className="profile-hero-img" />
        <div className="profile-avatar-wrap">
          <img
            src={user.profile_picture_url || DEFAULT_AVATAR}
            alt="Profile"
            className="profile-page-avatar"
          />
          {editable && (
            <>
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                className="avatar-upload__input"
                onChange={handleFileChange}
              />
              <button
                type="button"
                className="avatar-upload__overlay"
                onClick={handleUploadClick}
                aria-label="Upload new profile picture"
                disabled={uploading}
                title={uploading ? "Uploading…" : "Upload new picture"}
              >
                {uploading ? "Uploading…" : "⬆"}
              </button>
            </>
          )}
        </div>
      </div>

      <div className="profile-content">
        <div className="profile-title">
          <div className="profile-name">{user.first_name} {user.last_name}</div>
          <div className="profile-userid">User ID: {user.id}</div>
        </div>

        {stats && (
          <div className="profile-stats-card">
            <div className="stat-item">
              <div className="stat-value">{stats.friends}</div>
              <div className="stat-label">{statLabels?.friends ?? "Friends"}</div>
            </div>
            <div className="stat-item">
              <div className="stat-value">{stats.eventsAttended}</div>
              <div className="stat-label">{statLabels?.eventsAttended ?? "Events attended"}</div>
            </div>
          </div>
        )}

        {editable && (
          <div className="profile-small-link-row">
            <a className="profile-small-link" href="/events/registered">My registered events</a>
          </div>
        )}

        {children}
      </div>
    </>
  );
};

export default ProfileOverview;
