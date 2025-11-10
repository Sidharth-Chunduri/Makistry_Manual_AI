import { useState, useRef, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowUp } from "lucide-react";
import { Button } from "@/components/ui/button";
import { LandingTopBar } from "@/components/LandingTopBar";
import { ProjectsSection } from "@/components/ProjectsSection";
import { useAuth } from "@/hooks/useAuth";
import { AuthGateModal } from "@/components/AuthGateModal";
import { useProjects } from "@/hooks/useProjects";
import { CommunitySection } from "./CommunitySection";
import { queueAuthAction } from "@/lib/pendingActions";

import { useAccount } from "@/hooks/useAccount";
import { useCreditGate } from "@/stores/useCreditGate";
import { ActionGateModal } from "@/components/ActionGateModal";
import { Link } from "react-router-dom";

interface InitialInputProps {
  onSubmit: (query: string) => void;
  loading?: boolean;
}

export function InitialInput({ onSubmit, loading = false }: InitialInputProps) {
  const [query, setQuery] = useState("");
  const projectsRef = useRef<HTMLElement | null>(null);
  const { user } = useAuth();
  const [needAuth, setNeedAuth] = useState(false);
  const navigate = useNavigate();
  const nextPath = window.location.pathname + window.location.search;
  const { data: projects = [], isLoading: projLoading } =
    useProjects(!!user, user?.sub ?? null);

  /* NEW: account + gate hooks */
  const { data: me } = useAccount();
  const openGate = useCreditGate((s) => s.openGate);

  useEffect(() => {
    projectsRef.current = document.getElementById("projects") as HTMLElement | null;
  }, []);

  /* helpers for reset timestamps (so "Next reset" shows) */
  const dayResetAtISO = (() => {
    const d = new Date(); d.setHours(24, 0, 0, 0); return d.toISOString();
  })();
  const monthResetAtISO = (() => {
    const now = new Date(); const d = new Date(now.getFullYear(), now.getMonth() + 1, 1, 0, 0, 0, 0);
    return d.toISOString();
  })();

  const handleSubmit = (e?: React.FormEvent) => {
    e?.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) return;

    if (!user) {
      // Queue the brainstorm so it runs after auth
      queueAuthAction(
        { type: "brainstorm", payload: { prompt: trimmed } },
        nextPath
      );
      setNeedAuth(true);
      return;
    }

    // If account data isn't loaded yet, don't block — let backend enforce too.
    if (!me) {
      onSubmit(trimmed);
      return;
    }

    // --- CREDIT GATE: daily or monthly out? ---
    const dailyLeft     = me.creditsLeft ?? 0;
    const dailyQuota    = me.dailyQuota ?? 0;
    const creditsToday  = me.creditsToday ?? Math.max(0, dailyQuota - dailyLeft);

    const monthlyCap    = me.monthlyCreditsCap ?? 0; // cap (if provided)
    const monthlyUsed   = me.monthlyCredits ?? 0;    // used this month
    const monthlyRemaining = Math.max(0, (monthlyCap || 0) - monthlyUsed);

    const isDailyOut    = dailyLeft <= 0;
    const isMonthlyOut  = monthlyCap > 0 && monthlyRemaining <= 0;

    if (isDailyOut || isMonthlyOut) {
      openGate({
        plan: me.plan,
        limits: {
          dailyQuota,
          creditsLeft: dailyLeft,
          creditsToday,
          monthlyCap,
          monthlyUsed,
          monthlyRemaining,
          dayResetAtISO,
          monthResetAtISO,
        },
        banks: {
          rollover: me.bankRollover ?? 0,
          rewards: (me.bankRewards ?? me.creditsBank ?? 0) || 0,
        },
        gateFor: "brainstorm",
        onContinue: () => {
          // Resume the originally intended brainstorm
          onSubmit(trimmed);
        },
      });
      return;
    }

    // Already authed & within limits → run the original handler
    onSubmit(trimmed);
  };

  const isComposing = useRef(false);

  return (
    <div className="min-h-screen bg-primary-light">
      <LandingTopBar />
      <AuthGateModal
        open={needAuth}
        onClose={() => setNeedAuth(false)}
        onLogin={() => {
          setNeedAuth(false);
          navigate(`/login?next=${encodeURIComponent(nextPath)}`);
        }}
        onSignup={() => {
          setNeedAuth(false);
          navigate(`/signup?next=${encodeURIComponent(nextPath)}`);
        }}
      />
      <ActionGateModal />

      <section className="relative mx-auto max-w-3xl px-4 sm:px-6">
        <div className="min-h-[calc(100vh-64px-92px)] flex flex-col items-center justify-center">
          <h1 className="text-4xl font-bold text-primary text-center mb-10">
            What are we making today?
          </h1>

          <form onSubmit={handleSubmit} className="w-full">
            <div className="relative">
              {/* Bubble container */}
              <div className="relative w-full rounded-2xl border border-primary/20 bg-background shadow-sm overflow-hidden">
                <textarea
                  rows={1}
                  value={query}
                  onChange={(e) => {
                    setQuery(e.target.value);

                    // Auto-grow up to 5 lines, then scroll
                    const el = e.currentTarget;
                    const cs = window.getComputedStyle(el);
                    const line = parseFloat(cs.lineHeight || "20");
                    const padTop = parseFloat(cs.paddingTop || "0");
                    const padBot = parseFloat(cs.paddingBottom || "0");
                    const maxLines = 5;
                    const maxH = Math.round(line * maxLines + padTop + padBot);

                    el.style.height = "0px";
                    const next = Math.min(el.scrollHeight, maxH);
                    el.style.height = next + "px";
                    el.style.overflowY = el.scrollHeight > maxH ? "auto" : "hidden";
                  }}
                  onCompositionStart={() => (isComposing.current = true)}
                  onCompositionEnd={() => (isComposing.current = false)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey && !isComposing.current) {
                      e.preventDefault();
                      handleSubmit();
                    }
                  }}
                  placeholder="Describe your idea..."
                  autoFocus
                  disabled={loading}
                  className={[
                    "block w-full bg-transparent border-0 outline-none",
                    "text-base leading-relaxed",
                    "min-h-[52px]",
                    "pl-6 pr-[4rem] py-3 resize-none",
                    "focus:ring-0",
                  ].join(" ")}
                  style={{ overflowWrap: "anywhere", wordBreak: "break-word" }}
                  aria-label="Describe your idea"
                  data-gramm="false"
                  data-lt-active="false"
                  spellCheck
                />

                {/* Send button */}
                <button
                  type="submit"
                  disabled={loading || !query.trim()}
                  className="absolute right-2 top-1/2 -translate-y-1/2 inline-flex h-10 w-10 items-center justify-center rounded-2xl bg-primary text-white shadow-md ring-1 ring-black/10 hover:shadow-lg disabled:opacity-50"
                  aria-label="Submit"
                >
                  <ArrowUp className="h-5 w-5" />
                </button>
              </div>
            </div>
          </form>
        </div>
      </section>

      {user && (
        <>
          {projLoading ? (
            <p className="text-center py-10 text-sm text-muted-foreground">
              Loading your projects…
            </p>
          ) : (
            <ProjectsSection projects={projects} />
          )}
        </>
      )}
      <CommunitySection />
      <div className="bg-white flex flex-col items-center text-center space-y-5 pb-8">
        <img
          src="/Makistry.png"
          alt="Makistry logo"
          className="h-16 w-auto select-none"
        />
        <p className="text-md text-[#031926] font-light">© 2025 Makistry. All rights reserved.</p>
        <div className="flex gap-4 text-md font-light">
          <Link to="/privacy-policy" className="hover:underline">
            Privacy Policy
          </Link>
          <span className="text-[#031926]/60">|</span>
          <Link to="/terms-of-service" className="hover:underline">
            Terms of Service
          </Link>
        </div>
        <div className="flex gap-4">
          <Button
            asChild
            size="lg"
            className="p-0 hover:scale-120 rounded-lg transition-all duration-300 transform hover:scale-110 hover:bg-white bg-white"
          >
            <a
              href="https://www.linkedin.com/company/makistry"
              target="_blank"
              rel="noopener noreferrer"
            >
              <img src="/linkedin.png" alt="LinkedIn" className="h-10 w-10" />
            </a>
          </Button>
          <Button
            asChild
            size="lg"
            /* remove text padding, keep hover / border effects */
            className="p-0 hover:scale-120 rounded-lg transition-all duration-300 transform hover:scale-110 hover:bg-white bg-white"
          >
            <a
              href="https://www.youtube.com/@MakistryAI"
              target="_blank"
              rel="noopener noreferrer"
            >
              <img
                src="/yt.png"
                alt="Youtube"
                className="h-7 w-9"
              />
            </a>
          </Button>
          <Button asChild size="lg" className=" p-0 border-none bg-transparent rounded-lg transition-transform duration-300 hover:scale-110 hover:bg-white">
            <a href="mailto:contact@makistry.com">
              <img src="/mail.png" alt="Mail" className="h-8 w-8" />
            </a>
          </Button>
        </div>
      </div>
    </div>
  );
}
