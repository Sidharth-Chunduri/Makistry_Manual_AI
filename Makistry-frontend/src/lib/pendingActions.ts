// A tiny, typed “intent after auth” queue using sessionStorage.

// add new variants:
export type PendingAction =
  | {
      type: "remix";
      payload: {
        srcProjectId: string;
        cadVersion: number | null;
        brainVersion: number | null;
      };
    }
  | {
      type: "brainstorm";
      payload: {
        prompt: string;
      };
    }
  | {
      type: "like";
      payload: {
        projectId: string;
      };
    };


type PendingRecord = {
  id: string;
  createdAt: number;
  next: string;          // where to navigate immediately after auth
  action: PendingAction;
};

const KEY = "pendingAction";
const TTL_MS = 30 * 60 * 1000; // 30 minutes

export function queueAuthAction(action: PendingAction, nextPath: string) {
  const rec: PendingRecord = {
    id: crypto?.randomUUID?.() ?? Math.random().toString(36).slice(2),
    createdAt: Date.now(),
    next: nextPath,
    action,
  };
  sessionStorage.setItem(KEY, JSON.stringify(rec));
}

export function readPending(): PendingRecord | null {
  const raw = sessionStorage.getItem(KEY);
  if (!raw) return null;
  try {
    const rec = JSON.parse(raw) as PendingRecord;
    if (!rec?.action?.type || Date.now() - rec.createdAt > TTL_MS) {
      sessionStorage.removeItem(KEY);
      return null;
    }
    return rec;
  } catch {
    sessionStorage.removeItem(KEY);
    return null;
  }
}

export function clearPending() {
  sessionStorage.removeItem(KEY);
}

