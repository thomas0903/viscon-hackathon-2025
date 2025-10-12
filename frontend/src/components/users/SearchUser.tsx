import { useEffect, useState } from 'react';
import './SearchUser.css';
import { addFriend, getUser, searchUsers, type BackendUser } from '../../apiClient';

interface SearchUserProps {
  onClose: () => void;
  onAdded?: (user: BackendUser) => void;
  /** Optional override: perform custom action instead of addFriend */
  onAction?: (user: BackendUser) => Promise<void> | void;
  /** Label for the action button (defaults to "Add") */
  actionLabel?: string;
}

const SearchUser = ({ onClose, onAdded, onAction, actionLabel = 'Add' }: SearchUserProps) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<BackendUser[]>([]);
  const [isClosing, setIsClosing] = useState(false);
  const [addingId, setAddingId] = useState<string | null>(null);

  const beginClose = () => {
    if (isClosing) return;
    setIsClosing(true);
    window.setTimeout(() => onClose(), 280);
  };

  // Close on ESC
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') beginClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSearch = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const query = e.target.value;
    setSearchQuery(query);

    const trimmed = query.trim();
    // If user types a numeric ID, fetch that user
    const asNumber = Number.parseInt(trimmed, 10);
    if (!Number.isNaN(asNumber) && asNumber > 0) {
      try {
        const user = await getUser();
        setSearchResults([user]);
      } catch (_) {
        setSearchResults([]);
      }
      return;
    }

    // Otherwise search by name/username (allow from 1 character)
    if (trimmed.length >= 1) {
      try {
        const results = await searchUsers(trimmed, 10, 0);
        setSearchResults(results);
      } catch (_) {
        setSearchResults([]);
      }
    } else {
      setSearchResults([]);
    }
  };

  const handleAdd = async (user: BackendUser) => {
    if (addingId) return;
    try {
      setAddingId(String(user.id));
      if (onAction) {
        await onAction(user);
        onAdded?.(user);
      } else {
        await addFriend(user.id);
        onAdded?.(user);
      }
      beginClose();
    } finally {
      setAddingId(null);
    }
  };

  const hasQuery = searchQuery.trim().length > 0;
  const isNumericId = !Number.isNaN(Number.parseInt(searchQuery.trim(), 10));
  const showEmpty = hasQuery && searchResults.length === 0 && isNumericId;

  return (
    <div
      className={`search-overlay${isClosing ? ' is-closing' : ''}`}
      role="dialog"
      aria-modal="true"
      aria-labelledby="search-panel-title"
      onClick={beginClose}
    >
      {/* Side panel container; position via CSS (e.g., right drawer) */}
      <div className="search-panel search-panel--right" role="document" onClick={(e) => e.stopPropagation()}>
        <header className="search-panel__header">
          <h3 id="search-panel-title" className="search-panel__title">Search Users</h3>
          <button className="search-panel__close" onClick={beginClose} aria-label="Close">×</button>
        </header>

        <div className="search-panel__controls">
          <div className="search-input">
            <span className="search-input__icon" aria-hidden>
              🔍
            </span>
            <input
              type="text"
              placeholder="Search for users…"
              value={searchQuery}
              onChange={handleSearch}
              className="search-input__field"
              autoFocus
            />
          </div>
        </div>

        <div className="search-panel__body">
          {/* Results */}
          {searchResults.length > 0 && (
            <ul className="search-results" role="listbox">
              {searchResults.map((user) => (
                <li key={user.id} className="search-result" role="option" aria-selected={false}>
                  <img src={user.profile_picture_url || "/res/Portrait_Placeholder.png"} alt="" className="search-result__avatar" />
                  <div className="search-result__meta">
                    <div className="search-result__name">{`${user.first_name || ''} ${user.last_name || ''}`.trim() || user.username || `User ${user.id}`}</div>
                    <div className="search-result__desc">ID: {user.id}</div>
                  </div>
                  <button className="search-result__action" onClick={() => handleAdd(user)} disabled={addingId === user.id}>
                    {addingId === user.id ? `${actionLabel}…` : actionLabel}
                  </button>
                </li>
              ))}
            </ul>
          )}

          {/* Empty state */}
          {showEmpty && (
            <div className="search-empty">
              <div className="search-empty__icon" aria-hidden>🧐</div>
              <div className="search-empty__title">No users found</div>
              <div className="search-empty__hint">Try a different name or spelling.</div>
            </div>
          )}

          {/* Helper state */}
          {!hasQuery && (
            <div className="search-helper">
              <div className="search-helper__title">Search by name or username</div>
              <div className="search-helper__hint">Start typing to see results…</div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default SearchUser;
