import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { EventItem } from "../../pages/Events";
import { useCallback, useEffect, useState } from "react";
import "./EventPage.css";
import { joinEvent, leaveEvent, getMyAttendance } from "../../apiClient";
import { UsersList }  from "../users/UsersList";
import { type User } from "../../pages/Friends";


export default function EventPage({event}: {event: EventItem}) {
  const { id, title, description, category, date, location, mutualFriends, href, imageUrl } = event;
  const [joined, setJoined] = useState(false);

  console.log(mutualFriends)

  // Load current user's attendance status on mount, on id change, and on page show/focus
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const res = await getMyAttendance(id);
        if (!cancelled) setJoined(!!res.attending);
      } catch (_e) {
        // ignore; keep previous state
      }
    };

    load();

    const onFocus = () => { void load(); };
    const onPageShow = (_e: any) => { void load(); };
    const onVisibility = () => { if (document.visibilityState === "visible") void load(); };
    window.addEventListener("focus", onFocus);
    window.addEventListener("pageshow", onPageShow as any);
    document.addEventListener("visibilitychange", onVisibility as any);

    return () => {
      cancelled = true;
      window.removeEventListener("focus", onFocus);
      window.removeEventListener("pageshow", onPageShow as any);
      document.removeEventListener("visibilitychange", onVisibility as any);
    };
  }, [id]);

  const onToggleAttend = useCallback(async () => {
    if (!id) return;
    try {
      if (joined) {
        await leaveEvent(id);
        setJoined(false);
      } else {
        await joinEvent(id);
        setJoined(true);
      }
    } catch (e: any) {
      console.error(e);
    } 
  }, [id, joined]);

  return (
    <main className="event-page" aria-labelledby="event-title">
      <article itemScope itemType="https://schema.org/Event">
        {/* Hero */}
        {imageUrl ? (
          <div>
            <img src={imageUrl} alt="" role="presentation" itemProp="image" />
          </div>
        ) : (
          <div aria-hidden="true" />
        )}

        {/* Header */}
        <header>
          <div className="event-header">
            <h1 id="event-title" itemProp="name">{title}</h1>
            <button
              type="button"
              className={joined ? "event-cta--leave" : undefined}
              onClick={onToggleAttend}
            >
              { (joined ? "Leave Event" : "Join Event")}
            </button>
          </div>
          {/* Meta: force date & location on separate lines */}
          {(date || location) && (
            <div >
              {date && (
                <span>
                  <span aria-hidden>📅</span> <time itemProp="startDate">{date}</time>
                </span>
              )}
              {location && (
                <span>
                  <span aria-hidden>📍</span> <span itemProp="location">{location}</span>
                </span>
              )}
            </div>
          )}
        </header>

        {/* Info chips: category, mutual friends, id */}
        {(category || Array.isArray(mutualFriends) || id) && (
          <section aria-label="Event info">
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              {category && (
                <span style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 6,
                  padding: "6px 10px",
                  borderRadius: 9999,
                  background: "#eef2ff",
                  color: "#3730a3",
                  border: "1px solid #c7d2fe",
                  fontWeight: 600,
                  fontSize: ".9rem",
                }}>
                  🏷️ <span>{category}</span>
                </span>
              )}
              {mutualFriends.length > 0 && (
                <span style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 6,
                  padding: "6px 10px",
                  borderRadius: 9999,
                  background: "#ecfdf5",
                  color: "#065f46",
                  border: "1px solid #a7f3d0",
                  fontWeight: 700,
                  fontSize: ".9rem",
                }}>
                  🤝 <span>{mutualFriends.length} mutual friend{mutualFriends.length === 1 ? "" : "s"}</span>
                </span>
              )}
              {id && (
                <span style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 6,
                  padding: "6px 10px",
                  borderRadius: 9999,
                  background: "#f8fafc",
                  color: "#334155",
                  border: "1px solid #e2e8f0",
                  fontWeight: 600,
                  fontSize: ".9rem",
                }}>
                  #ID <span>{id}</span>
                </span>
              )}
            </div>
          </section>
        )}

        {/* External link action if available */}
        {href && (
          <section aria-label="Actions">
            <div style={{ display: "flex", gap: 12 }}>
              <a
                href={href}
                target="_blank"
                rel="noreferrer noopener"
                style={{
                  display: "inline-block",
                  padding: "10px 14px",
                  borderRadius: 10,
                  background: "#3b82f6",
                  color: "#fff",
                  fontWeight: 600,
                  textDecoration: "none",
                }}
              >
                Open link
              </a>
            </div>
          </section>
        )}

        {/* Long body as markdown (use description if that's what we have) */}
        {description && (
          <section>
            <h2 className="sr-only">Event details</h2>
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                a: (props) => {
                  const { href, children, ...rest } = props;
                  const isExternal = !!href && /^(https?:)?\/\//i.test(href);
                  return (
                    <a
                      {...rest}
                      href={href}
                      target={isExternal ? "_blank" : undefined}
                      rel={isExternal ? "noreferrer noopener" : undefined}
                    >
                      {children}
                    </a>
                  );
                },
              }}
            >
              {description}
            </ReactMarkdown>
          </section>
        )}
        {/* Attendees */}
        {mutualFriends && mutualFriends.length > 0 && (
          <section aria-labelledby="attendees-title">
            <h2 id="attendees-title">Friends attending</h2>
            <UsersList users={mutualFriends.map(toUser)} />
          </section>
        )}
      </article>
    </main>
  );
}


function toUser(raw: any): User {
  const id = String(raw?.external_id);
  const name = raw?.first_name + " " + raw?.last_name;
  const photo = raw?.profile_picture_url;

  return {
    key: id,
    id,
    name,
    photo
  } as User;
}
