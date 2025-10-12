import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App.tsx";
import "./index.css";

const THEME_KEY = "vis-theme";

function applyInitialTheme() {
  if (typeof window === "undefined") return;
  const root = document.documentElement;
  const stored = window.localStorage.getItem(THEME_KEY);
  const prefersDark = window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false;
  const shouldUseDark = stored ? stored === "dark" : prefersDark;
  root.classList.toggle("dark", shouldUseDark);
}

applyInitialTheme();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
