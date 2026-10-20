import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In dev, /api is proxied to the FastAPI backend so the browser only talks to one origin.
// In production the backend serves the built files itself (see Dockerfile), or set
// VITE_API_BASE at build time when the frontend is hosted separately.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
});
