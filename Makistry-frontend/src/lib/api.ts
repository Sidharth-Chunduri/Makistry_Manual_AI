// src/lib/api.ts
import axios from "axios";

/**
 * Base URL rules:
 *  - In the browser (Firebase Hosting), default to "/api" so rewrites hit Cloud Run.
 *  - In local dev / Node contexts, default to "http://localhost:8000".
 *  - Allow override via VITE_API_URL if you want a custom backend.
 */
const isBrowser = typeof window !== "undefined";

let baseURL =
  import.meta.env.VITE_API_URL ??
  (isBrowser ? "/api" : "http://localhost:8000");

// Safety: never use localhost in production pages
if (isBrowser) {
  const hn = window.location.hostname;
  if (baseURL?.includes("localhost") && hn !== "localhost") {
    baseURL = "/api";
  }
}

export const api = axios.create({
  baseURL: String(baseURL || "/api").replace(/\/$/, ""),
  withCredentials: true,
});

// Helper so the auth hook can push / clear the token globally
export function setAuthToken(token: string | null) {
  if (token) {
    api.defaults.headers.common.Authorization =
      token.startsWith("Bearer ") ? token : `Bearer ${token}`;
  } else {
    delete api.defaults.headers.common.Authorization;
  }
}

// Pick up a token on app load
try {
  setAuthToken(localStorage.getItem("jwt"));
} catch {
  // noop (SSR / non-browser)
}

export function getApiBase(): string {
  return api.defaults.baseURL!;
}

export function apiUrl(path: string): string {
  const base = getApiBase();                         // e.g. "/api" or "http://localhost:8000"
  const baseWithApi = base.endsWith("/api") ? base : `${base}/api`;
  return `${baseWithApi}${path.startsWith("/") ? "" : "/"}${path}`;
}