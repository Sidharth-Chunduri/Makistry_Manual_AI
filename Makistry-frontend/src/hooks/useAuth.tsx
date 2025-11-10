// src/hooks/useAuth.tsx
import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { jwtDecode } from "jwt-decode";
import { setAuthToken } from "@/lib/api";
import { ensureFirebaseSession, destroyFirebaseSession } from "@/lib/firebaseBridge";
import { auth } from "@/firebase";

type User = { sub: string; email: string };

interface AuthCtx {
  user: User | null;
  token: string | null;
  login: (t: string) => void;
  logout: () => void;
  firebaseReady: boolean;
}

const Ctx = createContext<AuthCtx | undefined>(undefined);

function getPayload(t: string | null): (User & { exp?: number }) | null {
  if (!t) return null;
  try {
    const p: any = jwtDecode(t);
    return { sub: p.sub, email: p.email, exp: p.exp };
  } catch {
    return null;
  }
}

function isExpired(exp?: number): boolean {
  if (!exp) return false;
  return Date.now() >= exp * 1000;
}

// Set window name immediately when module loads
try {
  if (typeof window !== "undefined" && !window.name) {
    window.name = "makistry-main";
  }
} catch {}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const initialToken = useMemo(
    () => (typeof window !== "undefined" ? localStorage.getItem("jwt") : null),
    []
  );
  const initialPayload = getPayload(initialToken);

  // If token is already expired on load, drop it immediately
  const bootToken = initialToken && !isExpired(initialPayload?.exp) ? initialToken : null;
  if (!bootToken && initialToken) {
    try { localStorage.removeItem("jwt"); } catch {}
  }

  const [token, setTok] = useState<string | null>(bootToken);
  const [user, setUser]  = useState<User | null>(() =>
    bootToken && initialPayload ? { sub: initialPayload.sub, email: initialPayload.email } : null
  );
  const [firebaseReady, setFirebaseReady] = useState(false);

  // Bootstrap axios header on mount/state changes
  useEffect(() => {
    setAuthToken(token);
  }, [token]);

  const login = (t: string) => {
    try { localStorage.setItem("jwt", t); } catch {}
    const p = getPayload(t);
    setTok(t);
    setUser(p ? { sub: p.sub, email: p.email } : null);
    setAuthToken(t);
  };

  const logout = () => {
    try { localStorage.removeItem("jwt"); } catch {}
    setTok(null);
    setUser(null);
    setAuthToken(null);
    setFirebaseReady(false);
    destroyFirebaseSession();
  };

  // Auto-logout at (or just after) expiry
  useEffect(() => {
    if (!token) return;
    const p = getPayload(token);
    if (!p?.exp) return;

    const ms = p.exp * 1000 - Date.now() - 500; // fire slightly before expiry
    if (ms <= 0) {
      logout();
      return;
    }
    const id = setTimeout(logout, ms);
    return () => clearTimeout(id);
  }, [token]);

  // Ensure Firebase is signed in if we have an app JWT
  useEffect(() => {
    let active = true;
    if (!token) {
      setFirebaseReady(false);
      return () => { active = false; };
    }
    // If Firebase already has a user, we’re good
    if (auth.currentUser) {
      setFirebaseReady(true);
      return () => { active = false; };
    }
    // Attempt to bridge the session
    ensureFirebaseSession(token)
      .then(() => { if (active) setFirebaseReady(true); })
      .catch(() => { if (active) setFirebaseReady(false); });
    return () => { active = false; };
  }, [token]);

  // Ensure window name is set (backup to module-level setting)
  useEffect(() => {
    try {
      if (!window.name) window.name = "makistry-main";
    } catch {}
  }, []);

  return (
    <Ctx.Provider value={{ user, token, login, logout, firebaseReady }}>
      {children}
    </Ctx.Provider>
  );
}

export function useAuth() {
  const context = useContext(Ctx);
  if (!context) {
    throw new Error("useAuth must be used inside <AuthProvider>");
  }
  return context;
}
