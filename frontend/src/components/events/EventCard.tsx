import { Link } from "react-router-dom";
import "./EventCard.css";
import {type EventItem} from "../../pages/Events";

/**
 * Minimal EventCard: whole card is a Link. Default route is
 * `/events/eventspage/{slug}` but can be overridden via `to`, `basePath`, `slug`.
 */
export function EventCard( event: EventItem) {
  const { id, title, date, location, mutualFriends, imageUrl } = event;
  const addS = mutualFriends.length === 1 ? "" : "s";

  return (
    <article className="ec-card">
      <Link to={`/events/eventpage/${encodeURIComponent(String(id))}`} state={{ event }} className="ec-link" aria-label={`Open ${title}`}>
        {/* Image */}
        <div className="ec-image">
          <img src={imageUrl} alt={title} loading="lazy" />
        </div>

        {/* Content */}
        <div className="ec-body">
          <h3 className="ec-title">{title}</h3>

          {(date || location) && (
            <div className="ec-meta">
              {date && (
                <span>
                  🗓️ <span>{date}</span>
                </span>
              )}
              {location && (
                <span>
                  📍 <span>{location}</span>
                </span>
              )}
            </div>
          )}

          {}
          {/* Footer: friends-going badge (left) + CTA (right) */}
          <div className="ec-footer">
            <span className="ec-button">View details</span>
            {Array.isArray(mutualFriends) && (
              <span
                className="ec-going"
                title={`${mutualFriends.length} friend${addS} going`}
                aria-label={`${mutualFriends.length} friend${addS} going`}
              >
                <span className="ec-going-dot" aria-hidden></span>
                <span className="ec-going-text">{mutualFriends.length} friend{addS} going</span>
              </span>
            )}
          </div>
        </div>
      </Link>
    </article>
  );
}

export default EventCard;