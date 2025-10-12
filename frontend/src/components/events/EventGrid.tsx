import { useMemo } from "react";
import { EventCard } from "./EventCard";
import type { EventItem } from "../../pages/Events";
import "./EventCard.css";

type EventGridProps = {
  events: EventItem[];
  className?: string;
};

function mutualFriendsCount(evt: any): number {
  const mf = (evt && (evt as any).mutualFriends) as unknown;
  if (Array.isArray(mf)) return mf.length;
  const n = typeof mf === "number" ? mf : Number(mf ?? 0);
  return Number.isFinite(n) ? n : 0;
}

export function EventGrid({ events, className }: EventGridProps) {
  const sorted = useMemo(() => {
    // do not mutate incoming props
    return [...events].sort((a, b) => mutualFriendsCount(b) - mutualFriendsCount(a));
  }, [events]);

  return (
    <section className={`ec-grid ${className ?? ""}`} role="list">
      {sorted.map((evt, idx) => (
        <EventCard key={evt.href ?? `${evt.title}-${idx}`} {...evt} />)
      )}
    </section>
  );
}
