import { useState, useEffect } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { TermsCheckbox } from "@/components/TermsCheckbox";
import { GoogleButton } from "@/components/GoogleButton";
import { createUserWithEmailAndPassword } from "firebase/auth";
import { auth } from "@/firebase";
import { exchangeIdToken } from "@/lib/firebaseAuth";
import { useAuth } from "@/hooks/useAuth";
import { sendMagicLink } from "@/lib/emailLink";
import { listenForAuthDone } from "@/lib/authChannel";

export default function Signup() {
  const nav       = useNavigate();
  const location  = useLocation();
  const search    = new URLSearchParams(location.search);
  const nextPath  = search.get("next") || "/";
  const [info, setInfo] = useState<string | null>(null);

  // legacy support
  const state = (location as any).state as { pendingQuery?: string } | undefined;

  const { login } = useAuth();

  const [email, setEmail]       = useState("");
  const [password, setPassword] = useState("");
  const [agree, setAgree]       = useState(false);
  const [err, setErr]           = useState<string | null>(null);
  const [loading, setLoading]   = useState(false);

  useEffect(() => {
    const stop = listenForAuthDone((token, next) => {
      login(token);
      nav(next || nextPath, { replace: true });
    });
    return stop;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSignup = async () => {
    try {
      setLoading(true);
      await sendMagicLink(email, nextPath);
      setErr(null);
      setInfo("Check your email for a sign-in link. Keep this tab open.");
    } catch (e: any) {
      setErr(e?.message ?? "Failed to send sign-in link");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen grid place-items-center bg-[#D6F3FF]">
      <div className="max-w-sm w-full p-6 bg-white rounded-xl shadow">
        <h1 className="text-xl font-semibold mb-4 text-left">Create your account</h1>

        {/* Google OAuth */}
        <GoogleButton
          onSuccess={() => {
            if (nextPath) nav(nextPath, { replace: true });
            else if (state?.pendingQuery) nav("/", { state: { replay: state.pendingQuery }, replace: true });
            else nav("/", { replace: true });
          }}
        />

        <div className="my-4 flex items-center gap-2">
          <div className="flex-1 h-px bg-gray-300" />
          <span className="text-xs uppercase text-gray-500">or</span>
          <div className="flex-1 h-px bg-gray-300" />
        </div>

        <Input
          type="email"
          placeholder="maker@example.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="mb-3"
        />

        <TermsCheckbox agreed={agree} onToggle={() => setAgree(!agree)} />

        {err && <p className="text-red-600 text-sm">{err}</p>}
        {info && <p className="text-green-600 text-sm">{info}</p>}

        <Button
          className="w-full mt-3 bg-[#FFCA85] text-black hover:bg-[#FFCA85]/80"
          disabled={loading || !agree || !email}
          onClick={handleSignup}
        >
          {loading ? "Sending link…" : "Continue with email"}
        </Button>

        <p className="mt-4 text-center text-sm">
          Already have an account?{" "}
          {/* Preserve ?next=… when switching to login */}
          <Link to={`/login${location.search}`} className="underline text-primary">
            Log in
          </Link>
        </p>
      </div>
    </div>
  );
}
