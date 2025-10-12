import { BrowserRouter as Router, Routes, Route, Navigate, Link, useLocation, useParams } from "react-router-dom";
import React from "react";
import Navbar from "./components/Navbar";
import Events from "./pages/Events";
import Network from "./pages/Network";
import Friends from "./pages/Friends";
import Profile from "./pages/Profile";
import Blocked from "./pages/Blocked";
import UserProfile from "./pages/UserProfile";
import ProfileById from "./pages/ProfileById";
import EventPage from "./components/events/EventPage";
import WheelOfFortune from "./pages/WheelOfFortune";
import RegisteredEvents from "./pages/RegisteredEvents";
import { getUserEvents, type BackendEvent } from "./apiClient";
import { parseDate, parseLocation } from "./constants/parseEventData";

function EventDetailsRoute() {
  const location = useLocation() as any;
  const params = useParams();
  const eventFromState = location.state?.event;
  const [loading, setLoading] = React.useState(false);
  const [event, setEvent] = React.useState<any>(eventFromState || null);

  // Fallback: if no state passed, fetch events and find by external_id from URL
  React.useEffect(() => {
    if (eventFromState || !params?.id) return;
    let cancelled = false;
    setLoading(true);
    getUserEvents()
      .then((items: BackendEvent[]) => {
        if (cancelled) return;
        const targetId = decodeURIComponent(String(params.id));
        const raw = items.find(e => String(e.id) === targetId || String(e.external_id) === targetId);
        if (!raw) return;
        // Minimal mapping to EventItem expected by EventPage
        const mapped = {
          id: String(raw.id ?? raw.external_id),
          title: raw.name ?? "Event",
          description: raw.description ?? "",
          category: raw.category ?? "",
          date: parseDate(raw.starts_at ?? "", raw.ends_at ?? "", raw.timezone ?? "UTC") || "",
          location: parseLocation(raw.location_name ?? ""),
          mutualFriends: raw.friends ?? [],
          href: raw.link_url ?? undefined,
          imageUrl: raw.poster_url ?? "",
        };
        setEvent(mapped);
      })
      .finally(() => setLoading(false));
    return () => { cancelled = true; };
  }, [eventFromState, params?.id]);

  if (!event) {
    return (
      <div style={{ padding: 16 }}>
        {loading ? "Loading event…" : (
          <>
            Event not found. Please open it from the <Link to="/events">Events</Link> page.
          </>
        )}
      </div>
    );
  }
  return <EventPage event={event} />;
}

function App() {
  return (
    <Router>
      <Navbar />
      <Routes>
        <Route path="/" element={<Navigate to="/events" />} />
        <Route path="/events" element={<Events />} />
        <Route path="/events/registered" element={<RegisteredEvents />} />
        <Route path="/events/eventpage/:id" element={<EventDetailsRoute />} />
        <Route path="/wheeloffortune" element={<WheelOfFortune />} />
        <Route path="/network" element={<Network />} />
        <Route path="/friends" element={<Friends />} />
        <Route path="/profile" element={<Profile />} />
        <Route path="/profile/id" element={<ProfileById />} />
        <Route path="/profile/:id" element={<UserProfile />} />
        <Route path="/profile/blocked" element={<Blocked />} />
      </Routes>
    </Router>

  );
}

export default App;
