import { useEffect, useState } from "react";
import type React from "react";
import { api, type BackendEvent } from "../apiClient";
import { UsersList, type User } from "../components/users/UsersList";
import { useNavigate } from "react-router-dom";

// Map BackendEvent -> UsersList.User row showing each registered event as a "user-like" item
function mapEventToUserRow(evt: BackendEvent): User {
  const title = evt.name || "Untitled event";
  return {
    id: evt.id.toString(),
    name: title,
    photo: evt.poster_url || "/res/wofTitle.png",
  };
}

const RegisteredEvents: React.FC = () => {
  const navigate = useNavigate();
  const [rows, setRows] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        setLoading(true);
        setError(null);
        const events: BackendEvent[] = await api.getRegisteredEvents();
        const mapped = events.map(mapEventToUserRow);
        if (!active) return;
        setRows(mapped);
      } catch (e: any) {
        if (!active) return;
        setError(e?.message || "Failed to load registered events");
      } finally {
        if (!active) return;
        setLoading(false);
      }
    }
    load();
    return () => { active = false; };
  }, []);

  return (
    <section className="friends-container">
      <div className="friends-scroll-container">
        {error && <div style={{ padding: 16, color: "#b00" }}>{error}</div>}
        {loading && !error && <div style={{ padding: 16 }}>Loading…</div>}
        {!loading && !error && (
          <UsersList
            users={rows}
            onClick={(id) => navigate(`/events/eventpage/${encodeURIComponent(id)}`)}
          />
        )}
      </div>
    </section>
  );
};

export default RegisteredEvents;
