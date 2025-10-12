import { useEffect, useMemo, useState } from "react";
import type React from "react";

import { EventGrid } from "../components/events/EventGrid";
import EventsPageHeader, { type EventsHeaderState } from "../components/events/EventsPageHeader";
import { getUserEvents} from "../apiClient";
import {parseDate, parseLocation, inTimeframeISO} from "../constants/parseEventData";
import "../components/events/EventsPageHeader.css";
import "./Events.css";
import type { User } from "./Friends";
import SpinWheel from "../animations/SpinWheel";

/**
 * Domain type we render in the grid. Keep this small and focused on UI needs.
 * Add/rename fields here without touching the UI components.
 */
export interface EventItem {
  id: string;                 // backend Event.id (e.g., "vis.ethz.ch:981")
  title: string;              // display name
  description: string;       // event description
  category: string;           // e.g., Sports, Music
  date: string;              // ISO string 
  location: string;          // human-friendly location 
  mutualFriends: User[];      // number of friends in common
  href?: string;              // link to details
  imageUrl: string;          // card cover image
  startAtISO?: string;       // raw ISO for filtering
}

/**
 * Adapter: normalize any backend shape into our EventItem.
 * Extend as your API evolves.
 */
function toEventItem(raw: any): EventItem {
  const id = String(raw?.id ?? raw?.external_id);
  const title = (raw?.name ?? "NoName Event");
  const description = (raw?.description ?? "Details will be available soon.");
  const category = (raw?.category ?? "Uncategorized");
  const date = parseDate(raw.starts_at, raw.ends_at, raw.timezone) || "Date TBD";
  const startAtISO = raw?.starts_at ?? undefined;
  const location = parseLocation(raw?.location_name ?? "Zurich, Switzerland");
  const mutualFriends: User[] = raw?.friends ?? [];
  const href = raw?.href ? String(raw.href) : undefined;
  const imageUrl = raw?.poster_url ?? undefined;

  return {
    id,
    title,
    description,
    category,
    date,
    location,
    mutualFriends,
    href,
    imageUrl,
    startAtISO
  } as EventItem;
}

/**
 * Data source hook. Swap internals with a real fetch later.
 * Keeps UI code unaware of where data comes from.
 */
function useEventsSource() {
  const [events, setEvents] = useState<EventItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const raw = await getUserEvents();
        const items = (raw ?? []).map(toEventItem);
        if (!cancelled) setEvents(items);
      } catch (e: any) {
        if (!cancelled) setError(e?.message ?? "Failed to load events");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, []);

  return { events, loading, error } as const;
}

function filterEvents(all: EventItem[], f: EventsHeaderState): EventItem[] {
  const q = f.query.trim().toLowerCase();
  const now = new Date();
  return all.filter((evt) => {
    if (q && !evt.title.toLowerCase().includes(q)) return false;
    if (f.category && f.category !== "All" && evt.category !== f.category) return false;
    if ((evt.mutualFriends?.length ?? 0) < (f.minMutual || 0)) return false;
    if (!inTimeframeISO(evt.startAtISO, f.timeframe, now)) return false;
    return true;
  });
}

const Events: React.FC = () => {
  const { events, loading, error } = useEventsSource();
  const [filters, setFilters] = useState<EventsHeaderState>({
    query: "",
    minMutual: 0,
    category: "All",
    timeframe: "any",
  });

  // Build categories from loaded events (unique, sorted)
  const categories = useMemo(() => {
    const set = new Set<string>();
    for (const e of events) if (e.category) set.add(e.category);
    return ["All", ...Array.from(set).sort((a, b) => a.localeCompare(b))];
  }, [events]);

  const filtered = useMemo(() => filterEvents(events, filters), [events, filters]);
  console.log(filtered.map(evt => evt.mutualFriends.length));

  return (
    <main className="events-page" role="main">
      {/* Background simplified: we removed extra layers for a single, unified bg */}

      {/* Centered content shell with top padding to clear the navbar */}
      <div className="events-shell event-side-padding">
        <SpinWheel
                    size={256}
                    // spinning={true}
                    speedSec={6}
                    // sticky={true}
                />
        {/* Elevated surface card that holds the header + grid */}
        <section className="events-surface" aria-label="Events list and filters">
          <EventsPageHeader
            title="Upcoming events"
            count={filtered.length}
            categories={categories}
            onChange={setFilters}
            initialQuery=""
            initialMinMutual={0}
            initialCategory="All"
            initialTimeframe="any"
          />

          {/* Inline banners that sit under the header */}
          {error && (
            <div className="events-banner events-banner--error" role="status">
              Failed to load events: {error}
            </div>
          )}
          {loading && !error && (
            <div className="events-banner events-banner--loading" role="status">
              Loading events…
            </div>
          )}

          {/* Grid wrapper for spacing and future layout tweaks */}
          <div className="events-grid-wrap">
            <EventGrid events={filtered} className="ec-grid--padded" />
          </div>
        </section>

        {/* Optional footer spacer for breathing room at the bottom */}
        <div className="events-footer-spacer" aria-hidden="true" />
      </div>
    </main>
  );
};

export default Events;
