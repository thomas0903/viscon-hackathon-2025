import { useEffect, useState } from "react";
import type React from "react";
import './FriendsPageHeader.css'

interface FriendsPageHeaderProps {
  /** Page title (defaults to "Friends") */
  title?: string;
  /** Optional count badge next to title */
  count?: number;
  /** Show the Add Friend button */
  showAddButton?: boolean;
  /** Click handler for the Add Friend button (e.g., open modal) */
  onAddFriend?: () => void;
  /** Label for the add button (defaults to "Add Friend") */
  addButtonLabel?: string;
  /** Callback fired whenever the search query changes */
  onSearchChange?: (query: string) => void;
  /** Initial search text controlled by parent if desired */
  initialQuery?: string;
  /** Placeholder for the search field (defaults to "Search friends…") */
  searchPlaceholder?: string;
}

const FriendsPageHeader: React.FC<FriendsPageHeaderProps> = ({
  title = "Friends",
  count,
  showAddButton = true,
  onAddFriend,
  onSearchChange,
  initialQuery = "",
  searchPlaceholder = "Search friends…",
  addButtonLabel = "Add Friend",
}) => {
  const [query, setQuery] = useState(initialQuery);

  useEffect(() => {
    setQuery(initialQuery);
  }, [initialQuery]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const next = e.target.value;
    setQuery(next);
    onSearchChange?.(next);
  };

  return (
    <header className="friends-header">
      <div className="friends-header__row">
        <div className="friends-title-wrap">
          <h1 className="friends-title">{title}</h1>
          {typeof count === "number" && (
            <span className="friends-count" aria-label="friends count">{count}</span>
          )}
        </div>

        {showAddButton && (
          <button
            type="button"
            className="add-friend-button btn btn--primary"
            onClick={onAddFriend}
          >
            <span className="btn__icon" aria-hidden="true">＋</span>
            <span className="btn__label">{addButtonLabel}</span>
          </button>
        )}
      </div>

      <div className="friends-search">
        <span className="friends-search__icon" aria-hidden="true">🔍</span>
        <label htmlFor="friends-search-input" className="sr-only">
          Search friends
        </label>
        <input
          id="friends-search-input"
          type="search"
          className="friends-search__input"
          placeholder={searchPlaceholder}
          value={query}
          onChange={handleChange}
          autoComplete="off"
        />
      </div>
    </header>
  );
};

export default FriendsPageHeader;
