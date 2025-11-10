// src/lib/tokenManager.ts
import { getAuth, onIdTokenChanged, User } from "firebase/auth";
import { api, setAuthToken } from "@/lib/api";
import { ensureFirebaseSession } from "@/lib/firebaseBridge";

type AppJwt = { token: string; exp: number }; // exp in seconds (JWT)

let current: AppJwt | null = null;
let timer: number | null = null;
let inflight: Promise<AppJwt> | null = null;

// simple subscriber list so AuthProvider can react if it wants
const listeners = new Set<(jwt: AppJwt | null) => void>();
export function onJwtChanged(cb: (jwt: AppJwt | null) => void) {
  listeners.add(cb);
  return () => listeners.delete(cb);
}
function notify() { for (const cb of listeners) cb(current); }

function decodeExp(jwt: string): number | null {
  try { return JSON.parse(atob(jwt.split(".")[1]))?.exp ?? null; } catch { return null; }
}
function readStored(): AppJwt | null {
  try {
    const raw = localStorage.getItem("jwt");
    if (!raw) return null;
    const exp = decodeExp(raw);
    if (!exp) return null;
    return { token: raw, exp };
  } catch { return null; }
}
function writeStored(jwt: AppJwt | null) {
  if (jwt) localStorage.setItem("jwt", jwt.token);
  else localStorage.removeItem("jwt");
}

function schedule(jwt: AppJwt) {
  if (timer) window.clearTimeout(timer);
  // refresh 10 minutes before exp (min 5s)
  const skew = 10 * 60_000;
  const dueMs = jwt.exp * 1000 - Date.now() - skew;
  timer = window.setTimeout(() => { void refresh(); }, Math.max(5_000, dueMs));
}

async function exchangeWithIdToken(user: User): Promise<AppJwt> {
  // Force-refresh Firebase ID token if close to exp
  const idToken = await user.getIdToken(true);
  const { data } = await api.post<{ token: string }>("/auth/firebase", { idToken });
  const token = data.token;
  const exp = decodeExp(token);
  if (!exp) throw new Error("Bad JWT from /auth/firebase");
  const jwt = { token, exp };

  // Use token for API, persist, and keep Firestore signed in (custom token flow)
  setAuthToken(token);
  writeStored(jwt);
  current = jwt;
  notify();

  // Make sure Firestore auth is alive (no-op if already valid)
  await ensureFirebaseSession(token);

  schedule(jwt);
  return jwt;
}

export async function refresh(): Promise<AppJwt> {
  if (inflight) return inflight;
  const auth = getAuth();
  const user = auth.currentUser;
  if (!user) throw new Error("No Firebase user");

  inflight = exchangeWithIdToken(user)
    .finally(() => { inflight = null; });
  return inflight;
}

export async function getJwtToken(): Promise<string | null> {
  // Use current if it’s valid for > 2 minutes
  const safe = 2 * 60_000;
  const jwt = current ?? readStored();
  if (jwt && Date.now() < jwt.exp * 1000 - safe) return jwt.token;

  try {
    const fresh = await refresh();
    return fresh.token;
  } catch {
    return jwt?.token ?? null; // last resort
  }
}

export async function getBearerHeader(): Promise<Record<string, string>> {
  const tok = await getJwtToken();
  return tok ? { Authorization: tok.startsWith("Bearer ") ? tok : `Bearer ${tok}` } : {};
}

/** Install a 401 retry-once interceptor on the shared axios client. */
export function installAxios401Retry(client = api) {
  client.interceptors.response.use(
    r => r,
    async (error) => {
      const resp = error?.response;
      // only retry once per request
      const cfg = error?.config || {};
      if (resp?.status === 401 && !cfg.__retried) {
        try {
          await refresh();                     // get a fresh app JWT
          const tok = await getJwtToken();
          if (tok) {
            cfg.headers = cfg.headers || {};
            cfg.headers.Authorization = `Bearer ${tok}`;
          }
          cfg.__retried = true;
          return client(cfg);
        } catch {
          // fall through to original error
        }
      }
      return Promise.reject(error);
    }
  );
}

/** Call this once at app bootstrap. */
export function initTokenManager() {
  // Prime from localStorage if present
  const initial = readStored();
  if (initial) {
    current = initial;
    setAuthToken(initial.token);
    schedule(initial);
  }

  // Keep JWT fresh whenever Firebase rotates its ID token
  onIdTokenChanged(getAuth(), async (user) => {
    if (!user) {
      if (timer) window.clearTimeout(timer);
      timer = null;
      current = null;
      writeStored(null);
      setAuthToken(null);
      notify();
      return;
    }
    try {
      // We only refresh immediately if close to exp; otherwise the timer handles it.
      const now = Date.now();
      const expMs = (current?.exp ?? 0) * 1000;
      if (!current || expMs - now < 10 * 60_000) {
        await refresh();
      }
    } catch (e) {
      // ignore; axios 401 retry will still handle during API calls
      // console.warn("JWT refresh onIdTokenChanged failed", e);
    }
  });

  // Optional: refresh on tab focus (covers long idle periods)
  const poke = () => { void getJwtToken(); };
  window.addEventListener("focus", poke);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") poke();
  });
}
