import type { BackendUser } from "../apiClient";

type Listener = (user: BackendUser | null) => void;

let currentUser: BackendUser | null = null;
const listeners = new Set<Listener>();

export function getCurrentUser(): BackendUser | null {
  return currentUser;
}

export function setCurrentUser(user: BackendUser | null): void {
  currentUser = user;
  for (const cb of Array.from(listeners)) {
    try { cb(currentUser); } catch { /* ignore */ }
  }
}

export function subscribe(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

