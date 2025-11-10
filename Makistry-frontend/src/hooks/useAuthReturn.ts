// src/hooks/useAuthReturn.ts
import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/hooks/useAuth";
import { listenForAuthDone } from "@/lib/authChannel";

type Options = { navigate?: boolean }; // default false

export function useAuthReturn(opts: Options = {}) {
  const { navigate = false } = opts;     // ← default: no navigation
  const { login } = useAuth();
  const nav = useNavigate();

  useEffect(() => {
    const stop = listenForAuthDone((token, next) => {
      login(token);                       // set JWT, ensure Firebase session
      if (navigate) {
        nav(next || "/", { replace: true });
      }
      // else: stay on the current page (no redirect)
      window.focus?.();
    });

    return () => stop();
  }, [login, nav, navigate]);
}
