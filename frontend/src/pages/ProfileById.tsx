import { useState } from "react";
import type React from "react";
import { useNavigate } from "react-router-dom";

const ProfileById: React.FC = () => {
  const [inputId, setInputId] = useState("");
  const navigate = useNavigate();

  const go = () => {
    const trimmed = inputId.trim();
    if (trimmed) {
      navigate(`/profile/${encodeURIComponent(trimmed)}`);
    }
  };

  return (
    <div className="profile-root" style={{ paddingTop: 24 }}>
      <div className="profile-form">
        <h3 className="profile-section-title">Open profile by ID</h3>
        <label className="profile-label">
          <span>User ID</span>
          <input
            className="profile-input"
            placeholder="Enter user id…"
            value={inputId}
            onChange={(e) => setInputId(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                go();
              }
            }}
          />
        </label>
        <button className="profile-save-btn" onClick={go}>View profile</button>
      </div>
    </div>
  );
};

export default ProfileById;

