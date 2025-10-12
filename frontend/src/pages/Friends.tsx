import { useState, useEffect } from "react";
import "./Friends.css";
import SearchUser from "../components/users/SearchUser";
import FriendsPageHeader from "../components/users/FriendsPageHeader";
import { UsersList } from "../components/users/UsersList";
import { armNextTomatoThrow } from "../animations/tomatoThrow";
import { getUserFriends, removeFriend, type BackendUser } from "../apiClient";

export interface User {
  id: string;
  name: string;
  photo: string;
}


/** Page component */
const Friends = () => {
  const userId = 1; // TODO: Get from authentication context or props
  const [friends, setFriends] = useState<User[]>([]);
  const [query, setQuery] = useState("");
  const [showSearch, setShowSearch] = useState(false);
  const [tomatoMode, setTomatoMode] = useState(false);

  useEffect(() => {
    getUserFriends()
      .then((apiFriends: BackendUser[]) => {
        const mappedFriends: User[] = apiFriends.map((bu: BackendUser) => ({
          id: bu.id.toString(),
          name: `${bu.first_name || ''} ${bu.last_name || ''}`.trim() || bu.username || `User ${bu.id}`,
          photo: bu.profile_picture_url || "/res/Portrait_Placeholder.png",
        }));
        setFriends(mappedFriends);
      })
      .catch((err) => {
        console.error('Failed to fetch friends:', err);
      });
  }, [userId]);

  const handleAddFriendClick = () => setShowSearch(true);
  const handleCloseSearch = () => setShowSearch(false);

  const handleAdded = (apiUser: BackendUser) => {
    const mapped: User = {
      id: apiUser.id.toString(),
      name: `${apiUser.first_name || ''} ${apiUser.last_name || ''}`.trim() || apiUser.username || `User ${apiUser.id}`,
      photo: apiUser.profile_picture_url || "/res/Portrait_Placeholder.png",
    };
    setFriends((prev) => {
      // de-dup if already present
      if (prev.some((u) => u.id === mapped.id)) return prev;
      return [...prev, mapped];
    });
    setShowSearch(false);
  };


  const handleRemove = async (id: string) => {
    try {
      await removeFriend(id);
      setFriends((prev) => prev.filter((f) => f.id !== id));
    } catch (err) {
      console.error('Failed to remove friend:', err);
    }
  };

  const filteredFriends = friends.filter(f => f.name.toLowerCase().includes(query.toLowerCase()));

  // Tomato toggle: when ON, arm the next throw on every mousedown (so the following click splashes)
  useEffect(() => {
    if (!tomatoMode) return;
    const opts = {
      imageUrl: "/res/tomato-tomato-throw.gif",
      size: 1000,
      throwDurationMs: 6000,
      holdMs: 600,
      fadeOutMs: 280,
      cursorOffset: { x: -180, y: -180 },
    } as const;
    const onMouseDown = (e: MouseEvent) => {
      const el = e.target as Element | null;
      if (el && el.closest && el.closest('[data-tomato-toggle]')) return; // don't arm when clicking the toggle
      armNextTomatoThrow(opts);
    };
    window.addEventListener('mousedown', onMouseDown, true);
    return () => window.removeEventListener('mousedown', onMouseDown, true);
  }, [tomatoMode]);

  // When tomato mode is ON, block other button/link clicks (except the toggle itself)
  useEffect(() => {
    if (!tomatoMode) return;
    const onClickBubble = (e: MouseEvent) => {
      const el = e.target as Element | null;
      if (el && el.closest && el.closest('[data-tomato-toggle]')) return;
      try {
        e.preventDefault();
        // Stop other handlers (e.g., React delegated onClick)
        if (typeof (e as any).stopImmediatePropagation === 'function') {
          (e as any).stopImmediatePropagation();
        }
        e.stopPropagation();
      } catch {}
    };
    document.addEventListener('click', onClickBubble, false);
    return () => document.removeEventListener('click', onClickBubble, false);
  }, [tomatoMode]);

  return (
    <section className="friends-container">
      <FriendsPageHeader
        count={filteredFriends.length}
        onAddFriend={handleAddFriendClick}
        onSearchChange={setQuery}
        initialQuery={query}
      />

      <div className="friends-scroll-container">
        <UsersList users={filteredFriends} onRemove={handleRemove} />
      </div>

      {showSearch && (
        <SearchUser onClose={handleCloseSearch} onAdded={handleAdded}/>
      )}
      <div className="tomato-toggle-wrap">
        <button
          type="button"
          data-tomato-toggle
          className={`profile-link-btn tomato-toggle-btn`}
          onClick={() => setTomatoMode((v) => !v)}
          title={tomatoMode ? "Tomato mode is ON" : "Enable tomato mode"}
        >
          {tomatoMode ? "Tomato mode: ON 🍅" : "Enable tomato mode 🍅"}
        </button>
      </div>
    </section>);
};

export default Friends;
