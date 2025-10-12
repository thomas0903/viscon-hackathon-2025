import { useEffect, useMemo, useState } from "react";
import type React from "react";
import "./EventsPageHeader.css";

export type EventsTimeframe = "any" | "today" | "this_week" | "this_month";

export interface EventsHeaderState {
  query: string;
  minMutual: number; // minimum number of friends in common
  category: string;  // event type/category key
  timeframe: EventsTimeframe; // simple third filter for when it's happening
}

export interface EventsPageHeaderProps {
  /** Main title, defaults to “Upcoming events”. */
  title?: string;
  /** Optional count badge next to title. */
  count?: number;

  /** Preload values (e.g., from URL params). */
  initialQuery?: string;
  initialMinMutual?: number;
  initialCategory?: string;
  initialTimeframe?: EventsTimeframe;

  /** Available categories to choose from (simple strings). */
  categories?: string[];

  /** Notifies parent whenever any filter/search value changes. */
  onChange?: (next: EventsHeaderState) => void;

  /** Optional: trigger add/create event flow. */
  onAddEvent?: () => void;
}

const DEFAULT_CATEGORIES = [
  "All",
  "Sports",
  "Music",
  "Tech",
  "Arts",
  "Social",
];

const EventsPageHeader: React.FC<EventsPageHeaderProps> = ({
  title = "Upcoming events",
  count,
  initialQuery = "",
  initialMinMutual = 0,
  initialCategory = "All",
  initialTimeframe = "any",
  categories = DEFAULT_CATEGORIES,
  onChange,
  onAddEvent,
}) => {
  const [query, setQuery] = useState(initialQuery);
  const [minMutual, setMinMutual] = useState<number>(initialMinMutual);
  const [category, setCategory] = useState<string>(initialCategory);
  const [timeframe, setTimeframe] = useState<EventsTimeframe>(initialTimeframe);

  const [minMutualDisplay, setMinMutualDisplay] = useState<string>(
    initialMinMutual && initialMinMutual > 0 ? String(initialMinMutual) : ""
  );

  const mutualHintId = "hint-filter-mutual";
  const categoryHintId = "hint-filter-category";
  const timeframeHintId = "hint-filter-timeframe"; // unused while timeframe control is hidden

  // Keep parent informed on any change
  useEffect(() => {
    onChange?.({ query, minMutual, category, timeframe });
  }, [query, minMutual, category, timeframe, onChange]);

  useEffect(() => {
    // keep display string consistent if minMutual was reset via clear
    setMinMutualDisplay(minMutual === 0 ? "" : String(minMutual));
  }, [minMutual]);

  const showCount = typeof count === "number";

  const hasActiveFilters = useMemo(() => {
    return (
      (query?.trim()?.length ?? 0) > 0 ||
      minMutual > 0 ||
      (category && category !== "All") ||
      timeframe !== "any"
    );
  }, [query, minMutual, category, timeframe]);

  const clearAll = () => {
    setQuery("");
    setMinMutual(0);
    setCategory("All");
    setTimeframe("any");
    setMinMutualDisplay("");
  };

  return (
    <header className="events-header" role="region" aria-label="Events filters and search">
      {/* Title row */}
      <div className="events-header__row">
        <div className="events-title-wrap">
          <h1 className="events-title">{title}</h1>
          {showCount && <span className="events-count" aria-label="events count">{count}</span>}
        </div>

        <div className="events-actions">
          {hasActiveFilters && (
            <button type="button" className="btn btn--ghost events-clear" onClick={clearAll}>
              Clear
            </button>
          )}
          {onAddEvent && (
            <button type="button" className="btn btn--primary events-add" onClick={onAddEvent}>
              <span className="btn__icon" aria-hidden>＋</span>
              <span className="btn__label">Create event</span>
            </button>
          )}
        </div>
      </div>

      {/* Controls: search + filters in one bar */}
      <div className="events-controls">
        {/* Search */}
        <div className="events-search" role="search">
          <span className="events-search__icon" aria-hidden>🔎</span>
          <label htmlFor="events-search-input" className="sr-only">Search events</label>
          <input
            id="events-search-input"
            className="events-search__input events-control__field"
            type="search"
            placeholder="Search events by name…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            autoComplete="off"
          />
        </div>

        {/* Filter: min mutual friends */}
        <div className="events-filter events-control events-control--with-hint">
          <div id={mutualHintId} className="events-control__hint">Friends going (at least)</div>
          <label htmlFor="filter-mutual" className="sr-only">Min mutual friends</label>
          <input
            id="filter-mutual"
            className="events-filter__input events-control__field"
            type="number"
            inputMode="numeric"
            min={0}
            max={99}
            placeholder="0"
            aria-describedby={mutualHintId}
            value={minMutualDisplay}
            onChange={(e) => {
              const v = e.target.value;
              // Allow empty string for placeholder to show
              setMinMutualDisplay(v);
              const n = Number(v);
              if (v === "" || isNaN(n)) {
                setMinMutual(0);
              } else {
                setMinMutual(Math.max(0, n));
              }
            }}
            onBlur={() => {
              // Normalize on blur: show empty if 0, else the number
              setMinMutualDisplay(minMutual === 0 ? "" : String(minMutual));
            }}
          />
        </div>

        {/* Filter: category */}
        <div className="events-filter events-control events-control--with-hint">
          <div id={categoryHintId} className="events-control__hint">Category</div>
          <label htmlFor="filter-category" className="sr-only">Category</label>
          <select
            id="filter-category"
            className="events-filter__select events-control__field"
            aria-label="Category"
            aria-describedby={categoryHintId}
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            data-multi-capable="false" /* later: switch to multiple */
          >
            {categories.map((cat) => (
              <option key={cat} value={cat}>{cat}</option>
            ))}
          </select>
        </div>

        {/* Filter: timeframe */}
        <div className="events-filter events-control events-control--with-hint">
          <div id={timeframeHintId} className="events-control__hint">Date</div>
          <label htmlFor="filter-timeframe" className="sr-only">When</label>
          <select
            id="filter-timeframe"
            className="events-filter__select events-control__field"
            aria-label="When"
            aria-describedby={timeframeHintId}
            value={timeframe}
            onChange={(e) => setTimeframe(e.target.value as EventsTimeframe)}
            data-multi-capable="false"
          >
            <option value="any">Any time</option>
            <option value="today">Today</option>
            <option value="this_week">This week</option>
            <option value="this_month">This month</option>
          </select>
        </div>
      </div>
    </header>
  );
};

export default EventsPageHeader;
