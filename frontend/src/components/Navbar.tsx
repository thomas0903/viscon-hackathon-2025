import { useEffect, useRef, useState } from "react";
import type React from "react";
import { NavLink, Link, useLocation } from "react-router-dom";
import "./Navbar.css";
import ThemeToggle from "./ThemeToggle";
import { api, type BackendUser } from "../apiClient";
import { subscribe, setCurrentUser as storeSetUser, getCurrentUser } from "../state/currentUser";

const Navbar: React.FC = () => {
  const location = useLocation();
  const listRef = useRef<HTMLUListElement | null>(null);
  const [indicatorStyle, setIndicatorStyle] = useState<{ left: number; width: number }>({ left: 0, width: 0 });

  const [user, setUser] = useState<BackendUser | null>(null);

  useEffect(() => {
    const listEl = listRef.current;
    if (!listEl) return;
    const active = listEl.querySelector<HTMLAnchorElement>(".nav-link.is-active");
    if (!active) return;
    const listBox = listEl.getBoundingClientRect();
    const activeBox = active.getBoundingClientRect();
    const left = activeBox.left - listBox.left; // relative position within the list
    const width = activeBox.width;
    setIndicatorStyle({ left, width });
  }, [location.pathname]);

  // Load current user and subscribe for changes
  useEffect(() => {
    let active = true;
    // seed from store if available
    setUser(getCurrentUser());
    api.getUser().then((u) => {
      if (!active) return;
      setUser(u);
      storeSetUser(u);
    }).catch(() => { /* ignore */ });
    const unsub = subscribe((u) => setUser(u));
    return () => { active = false; unsub(); };
  }, []);

  return (
    <nav className="navbar">
      <Link to="/" className="nav-logo-link" aria-label="Go to homepage">
        <img src="/logo_black.png" alt="EventLoupe Logo" className="logo logo--light" height={60} width={190}/>
        <img src="/logo_white.png" alt="EventLoupe Logo" className="logo logo--dark" height={60} width={190}/>
      </Link>
      <ul className="nav-links" ref={listRef}>
        {!location.pathname.startsWith("/profile") && indicatorStyle.width > 0 && (
          <span
            className="nav-indicator"
            style={{ transform: `translateX(${indicatorStyle.left}px)`, width: indicatorStyle.width }}
          />
        )}
        <li>
          <NavLink
            to="/events"
            end
            className={({ isActive }) => (location.pathname.startsWith("/profile") ? "nav-link" : isActive ? "nav-link is-active" : "nav-link")}
          >
            Events
          </NavLink>
        </li>
        <li>
        </li>
        <li>
          <NavLink
            to="/network"
            end
            className={({ isActive }) => (location.pathname.startsWith("/profile") ? "nav-link" : isActive ? "nav-link is-active" : "nav-link")}
          >
            Network
          </NavLink>
        </li>
        <li>
          <NavLink
            to="/friends"
            end
            className={({ isActive }) => (location.pathname.startsWith("/profile") ? "nav-link" : isActive ? "nav-link is-active" : "nav-link")}
          >
            Friends
          </NavLink>
        </li>
      </ul>
      <div className="nav-actions">
        <ThemeToggle />
      </div>
      <Link to="/profile" className="nav-profile" aria-label="Open profile">
        <img
          src={user?.profile_picture_url || "/res/Portrait_Placeholder.png"}
          alt="User avatar"
          className="profile-avatar"
          width={32}
          height={32}
          loading="lazy"
          referrerPolicy="no-referrer"
        />
      </Link>
    </nav>
  );
};

export default Navbar;
