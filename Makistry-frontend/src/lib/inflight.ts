// src/lib/inflight.ts
// Tiny per-project "in-flight" store backed by sessionStorage.

export type InflightKind = "codegen";
type Kind = InflightKind;

// Store shape: projectId -> { kind?: expiresAtMs }
type Store = Record<string, Partial<Record<Kind, number>>>;

const KEY = "inflightStore";

function read(): Store {
  try {
    const raw = sessionStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as Store) : {};
  } catch {
    return {};
  }
}

function write(s: Store) {
  sessionStorage.setItem(KEY, JSON.stringify(s));
}

function now() {
  return Date.now();
}

/** Mark a project/kind as in-flight for ttlMs (default 15m). */
export function setInFlight(kind: Kind, projectId: string, ttlMs = 15 * 60 * 1000) {
  if (!projectId) return;
  const s = read();
  s[projectId] = s[projectId] || {};
  s[projectId]![kind] = now() + ttlMs;
  write(s);
}

/** Clear in-flight flag. Safe if missing. */
export function clearInFlight(kind: Kind, projectId: string) {
  if (!projectId) return;
  const s = read();
  if (!s[projectId]) return;
  delete s[projectId]![kind];
  if (Object.keys(s[projectId]!).length === 0) delete s[projectId];
  write(s);
}

/** True if currently marked in-flight and not expired. */
export function isInFlight(kind: Kind, projectId?: string | null) {
  if (!projectId) return false;
  const s = read();
  const exp = s[projectId]?.[kind];
  if (!exp) return false;
  if (exp < now()) {
    clearInFlight(kind, projectId);
    return false;
  }
  return true;
}
