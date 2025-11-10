// src/pages/FinishLogin.tsx
import { useEffect, useState } from "react";
import { isSignInWithEmailLink, signInWithEmailLink } from "firebase/auth";
import { auth } from "@/firebase";
import { exchangeIdToken } from "@/lib/firebaseAuth";
import { notifyAuthDone } from "@/lib/authChannel";
import { Check } from "lucide-react";

export default function FinishLogin() {
  const [email, setEmail] = useState(localStorage.getItem("emailForSignIn") || "");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(true);
  const [done, setDone] = useState(false);

  useEffect(() => {
    const run = async () => {
      try {
        // Validate this is a Firebase email-sign-in link
        if (!isSignInWithEmailLink(auth, window.location.href)) {
          setErr("Invalid or expired sign-in link.");
          setBusy(false);
          return;
        }

        // Get/confirm email
        let em = email;
        if (!em) em = window.prompt("Confirm your email to complete sign-in") || "";
        if (!em) {
          setErr("Email confirmation cancelled.");
          setBusy(false);
          return;
        }
        setEmail(em);

        // Complete Firebase sign-in
        const cred = await signInWithEmailLink(auth, em, window.location.href);
        localStorage.removeItem("emailForSignIn");

        // Exchange Firebase ID token for your app JWT
        const idt = await cred.user.getIdToken();
        const jwt_ = await exchangeIdToken(idt);

        // 🔔 Notify the original tab to log in & continue there.
        // (BroadcastChannel + localStorage fallback)
        notifyAuthDone(jwt_, new URLSearchParams(window.location.search).get("next") || "/");

        // Optional: if you registered a service worker and want a nudge, you can ping it:
        // try {
        //   if ("serviceWorker" in navigator) {
        //     const reg = await navigator.serviceWorker.ready;
        //     reg.active?.postMessage({ type: "AUTH_DONE", next: "/" });
        //   }
        // } catch {}

        setDone(true);
        setBusy(false);

        // 🚫 No redirects/focus/close here. We just show instructions.

      } catch (e: any) {
        console.error("FinishLogin error:", e);
        setErr(e?.message ?? "Could not finish sign-in.");
        setBusy(false);
      }
    };
    run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (busy) {
    return (
      <div className="min-h-screen grid place-items-center bg-[#D6F3FF]">
        <div className="max-w-sm w-full p-6 bg-white rounded-xl shadow text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#FFCA85] mx-auto mb-4"></div>
          <h1 className="text-xl font-semibold mb-2">Signing you in…</h1>
          <p className="text-sm text-gray-600">One moment.</p>
        </div>
      </div>
    );
  }

  if (err) {
    return (
      <div className="min-h-screen grid place-items-center bg-[#D6F3FF]">
        <div className="max-w-sm w-full p-6 bg-white rounded-xl shadow text-center">
          <h1 className="text-xl font-semibold mb-2 text-red-600">Sign-in Failed</h1>
          <p className="text-sm text-red-600 mb-4">{err}</p>
          <button
            className="px-4 py-2 rounded bg-[#FFCA85] hover:bg-[#FFCA85]/80 text-black w-full"
            onClick={() => (window.location.href = `/login${window.location.search}`)}
          >
            Try Again
          </button>
        </div>
      </div>
    );
  }

  // ✅ Success: plain instructions, no navigation
  return (
    <div className="min-h-screen grid place-items-center bg-[#D6F3FF]">
      <div className="max-w-sm w-full p-6 bg-white rounded-xl shadow text-center">
        <div className="text-4xl mb-4 items-center justify-center flex">
          <Check className="text-green-500 w-6 h-auto" />
        </div>
        <h1 className="text-xl font-semibold mb-2">Success! You’re signed in</h1>
        <p className="text-sm text-gray-700 mb-4 font-medium">
          Please close this window and return to the Makistry tab.
        </p>
        <button
          className="px-4 py-2 rounded border bg-[#FFCA85] border-black-300 hover:bg-[#FFCA85]/80 text-black w-full text-sm"
          onClick={() => window.close()}
        >
          Close This Tab
        </button>
        {!done && (
          <p className="text-xs text-gray-500 mt-3">
            If this tab doesn’t close, you can close it manually.
          </p>
        )}
      </div>
    </div>
  );
}
