import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // Forward all requests to the backend server
      "/api": "http://localhost:8000",
      "/uploads": "http://localhost:8000",
    },
  },
});
