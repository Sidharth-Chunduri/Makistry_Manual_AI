// src/lib/authChannel.ts
const CH_NAME = "makistry-auth";

/** Send JWT to other tabs (original tab will handle login). */
export function notifyAuthDone(token: string, next: string) {
  // 1) BroadcastChannel (modern)
  try {
    const bc = new BroadcastChannel(CH_NAME);
    bc.postMessage({ type: "authed", token, next: next || "/", t: Date.now() });
    bc.close();
  } catch {}

  // 2) localStorage fallback (fires "storage" in other tabs)
  try {
    const key = "__makistry_auth_done__";
    localStorage.setItem(key, JSON.stringify({ token, next: next || "/", t: Date.now() }));
    setTimeout(() => { try { localStorage.removeItem(key); } catch {} }, 120);
  } catch {}
}

/** Receive JWT from FinishLogin tab. Returns a cleanup fn. */
export function listenForAuthDone(onDone: (token: string, next: string) => void) {
  let bc: BroadcastChannel | null = null;

  // BroadcastChannel
  try {
    bc = new BroadcastChannel(CH_NAME);
    bc.onmessage = (ev) => {
      const m = ev?.data ?? {};
      if (m?.type === "authed" && m?.token) onDone(m.token, m.next || "/");
    };
  } catch {}

  // localStorage
  const onStorage = (e: StorageEvent) => {
    if (e.key !== "__makistry_auth_done__" || !e.newValue) return;
    try {
      const m = JSON.parse(e.newValue);
      if (m?.token) onDone(m.token, m.next || "/");
    } catch {}
  };
  window.addEventListener("storage", onStorage);

  return () => {
    try { bc?.close(); } catch {}
    window.removeEventListener("storage", onStorage);
  };
}
