import { useState, useEffect } from "react";
import type React from "react";
import "./Profile.css";
import { UsersList, type User as ListUser } from "../components/users/UsersList";
import FriendsPageHeader from "../components/users/FriendsPageHeader";
import SearchUser from "../components/users/SearchUser";
import { api, type BackendUser } from "../apiClient";

const Blocked: React.FC = () => {
  const [blockedUsers, setBlockedUsers] = useState<ListUser[]>([]);
  const [query, setQuery] = useState("");
  const [showSearch, setShowSearch] = useState(false);

  // Load blocked users from backend
  useEffect(() => {
    api.getBlockedUsers()
      .then((users: BackendUser[]) => {
        const mapped: ListUser[] = users.map((u) => ({
          id: u.id.toString(),
          name: `${u.first_name || ''} ${u.last_name || ''}`.trim() || u.username || `User ${u.id}`,
          photo: u.profile_picture_url || "/res/Portrait_Placeholder.png",
        }));
        setBlockedUsers(mapped);
      })
      .catch((err) => {
        console.error('Failed to load blocked users:', err);
      });
  }, []);

  const handleRemove = async (id: string) => {
    try {
      await api.unblockUser(id);
      setBlockedUsers((prev) => prev.filter((u) => u.id !== id));
    } catch (err) {
      console.error('Failed to unblock user:', err);
    }
  };

  const filteredBlocked = blockedUsers.filter((u) =>
    u.name.toLowerCase().includes(query.toLowerCase())
  );

  return (
    <div className="profile-root" style={{ paddingTop: 24 }}>
      <div className="profile-form">
        <FriendsPageHeader
          title="Blocked"
          count={filteredBlocked.length}
          showAddButton={true}
          onAddFriend={() => setShowSearch(true)}
          onSearchChange={setQuery}
          initialQuery={query}
          searchPlaceholder="Search blocked users…"
          addButtonLabel="Block users"
        />
        {filteredBlocked.length === 0 ? (
          <div className="blocklist-empty">No blocked users.</div>
        ) : (
          <UsersList users={filteredBlocked} onRemove={handleRemove} />
        )}
      </div>
      {showSearch && (
        <SearchUser
          onClose={() => setShowSearch(false)}
          actionLabel="Block"
          onAction={async (user) => {
            const res = await api.blockUser(user.id);
            const u = res.user || user;
            const item: ListUser = {
              id: u.id.toString(),
              name: `${u.first_name || ''} ${u.last_name || ''}`.trim() || u.username || `User ${u.id}`,
              photo: u.profile_picture_url || "/res/Portrait_Placeholder.png",
            };
            // Add if not already in list
            setBlockedUsers((prev) => (prev.some((x) => x.id === item.id) ? prev : [...prev, item]));
          }}
        />
      )}
    </div>
  );
};

export default Blocked;
