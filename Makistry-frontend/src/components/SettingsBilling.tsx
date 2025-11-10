// src/components/settings/SettingsBilling.tsx
import { useEffect, useState } from "react";
import { getMe, setPlan, type Plan } from "@/lib/api/account";
import { PLAN_META, planRank } from "@/lib/plans";
import { Button } from "@/components/ui/button";
import { CheckCircle2, ExternalLink, Play, Info } from "lucide-react";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { AccountMe } from "@/lib/api/account";
import { useAuth } from "@/hooks/useAuth";
import { getBearerHeader } from "@/lib/tokenManager";

export function SettingsBilling() {
  const [loading, setLoading] = useState(true);
  const [plan, setPlanState]  = useState<Plan>("free");
  const [me, setMe] = useState<Awaited<ReturnType<typeof getMe>> | null>(null);
  const [busyPlan, setBusyPlan] = useState<"plus" | "pro" | "portal" | null>(null);

  const { user, token } = useAuth();
  // Get auth header for protected API routes (use app JWT, not Firebase user)
  const getAuthHeaders = async () => {
    // Prefer the token already in context; fall back to tokenManager
    if (token) {
      return { Authorization: token.startsWith("Bearer ") ? token : `Bearer ${token}` };
    }
    const hdr = await getBearerHeader(); // { Authorization: "Bearer <jwt>" } or {}
    if (!hdr.Authorization) throw new Error("Missing token");
    return hdr;
  };


  const dailyLeft = me?.creditsLeft ?? 0;
  const dailyTot  = me?.dailyQuota ?? 0;

  const bankCap   = me?.bankCap ?? 0;
  const dailyPct  = Math.min(100, dailyTot ? (dailyLeft / dailyTot) * 100 : 0);

  const roll      = me?.bankRollover ?? 0;
  const rewards   = me?.bankRewards ?? me?.creditsBank ?? 0; // fallback to legacy

  const eomLabel = (() => {
    const iso = (me as any)?.bankExpiryISO as string | undefined;
    if (!iso) return "Resets month-end";
    try {
      const d = new Date(`${iso}T23:59:59`);
      return `Resets ${d.toLocaleDateString(undefined, { month: "short", day: "numeric" })}`;
    } catch { return "Resets month-end"; }
  })();

  const al   = (me as any)?.actionLimits as AccountMe["actionLimits"] | undefined;
  const stl  = al?.month?.stl;
  const step = al?.month?.step;
  const proj = al?.week?.projects;

  function resetShort(iso?: string) {
    if (!iso) return "";
    try {
      const d = new Date(iso);
      return `Resets ${d.toLocaleDateString(undefined, { month: "short", day: "numeric" })}`;
    } catch { return ""; }
  }

  function usedCap(u?: number, c?: number | null) {
    if (u == null) u = 0;
    if (c == null) return `${u} / ∞`;
    return `${u} / ${c}`;
  }

    async function startCheckout(next: "plus" | "pro") {
    try {
      setBusyPlan(next);
      // 1) Pre-open the tab *synchronously* (before any await)
      const win = window.open("", "_blank"); // no features → get a real handle
      if (win) {
        win.document.title = "Redirecting to Stripe…";
        win.document.body.innerHTML =
          "<p style='font:14px system-ui, sans-serif;margin:1.5rem'>Redirecting to Stripe…</p>";
      }
      const headers = await getAuthHeaders();
      const res = await fetch("/api/billing/checkout", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers },
        body: JSON.stringify({ plan: next }),
      });
      if (!res.ok) {
        const err = await res.text();
        if (win && !win.closed) win.close();
        throw new Error(err || "Failed to start checkout");
      }
      const { url } = await res.json();
      if (!url) {
        if (win && !win.closed) win.close();
        throw new Error("Missing checkout URL");
      }
      if (win && !win.closed) {
        win.location.replace(url);
        try { win.focus(); } catch {}
      } else {
        // blocker fallback
        window.open(url, "_blank");
      }
    } catch (e) {
      setBusyPlan(null);
      throw e;
    }
  }

  // Open Stripe Customer Portal to manage/cancel/downgrade
  async function managePaymentPrefs() {
    try {
      setBusyPlan("portal");
      const win = window.open("", "_blank");
      if (win) {
        win.document.title = "Opening billing portal…";
        win.document.body.innerHTML =
          "<p style='font:14px system-ui, sans-serif;margin:1.5rem'>Opening billing portal…</p>";
      }
      const headers = await getAuthHeaders();
      const r = await fetch("/api/billing/portal", {
        method: "POST",
        headers,
      });
      if (!r.ok) {
        if (win && !win.closed) win.close();
        throw new Error(await r.text());
      }
      const { url } = await r.json();
      if (!url) {
        if (win && !win.closed) win.close();
        throw new Error("Missing portal URL");
      }
      if (win && !win.closed) win.location.replace(url);
      else window.open(url, "_blank");
    } catch (e) {
      alert("Manage billing not available yet. Email contact@makistry.com");
      setBusyPlan(null);
    }
  }

  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const m = await getMe();
        setMe(m);
        setPlanState((m.plan || "free").toLowerCase() as Plan);
      } catch {
        // Signed out or transient error — leave `me` as null and default plan "free"
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  // After Stripe redirects back with ?status=success|cancel, refresh account
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const status = params.get("status");
    if (status === "success") {
      (async () => {
        try {
          const m = await getMe();
          setMe(m);
          setPlanState((m.plan || "free").toLowerCase() as Plan);
        } catch {}
      })();
    }
  }, []);

  function cap(s: string) { return s.charAt(0).toUpperCase() + s.slice(1); }

  async function choosePlan(next: Plan) {
    // Only used for switching to FREE without Stripe (if you really want it).
    // For paid plans we use Stripe Checkout; for downgrades we use the portal.
    const res = await setPlan(next);
    setPlanState(res.plan);
    const m = await getMe();
    setMe(m);
  }

  if (loading) return <p className="text-sm text-muted-foreground">Loading…</p>;

  return (
    <>
      <div className="mb-4 flex items-center justify-between">
        <div>
          <p className="text-xs uppercase tracking-wide text-muted-foreground">Current plan</p>
          <p className="text-lg font-semibold">{cap(plan)}</p>
        </div>

        {/* Right side: Manage + Learn more (stacked) */}
        <div className="flex flex-col items-end gap-3">
          {plan !== "free" && (
            <Button
              variant="link"
              className="h-auto p-0"
              onClick={managePaymentPrefs}
              disabled={busyPlan === "portal"}
            >
              Manage subscription
              <ExternalLink className="ml-1 h-4 w-4" />
            </Button>
          )}
          <Button variant="link" className="h-auto p-0">
            <a href="mailto:contact@makistry.com" className="inline-flex items-center">
              Contact us for extra credits
              <ExternalLink className="ml-1 h-4 w-4" />
            </a>
          </Button> 

          <Button asChild variant="outline" className="pt-2 h-auto p-2">
            <a
              href="https://makistry.com/info"
              target="_blank"
              rel="noopener noreferrer"
            >
              <Info className="ml-1 h-4 w-4" />
              Learn more
            </a>
          </Button>
        </div>
      </div>

      {/* Credit overview stays EXACT for signed-in; fully hidden when signed out */}
      {user && (
        <div className="rounded-2xl border bg-card p-4 shadow-sm">
          <p className="text-base font-medium mb-3">Credit overview</p>

          <TooltipProvider delayDuration={150}>
            <div className="grid grid-cols-1 md:grid-cols-4 xl:grid-cols-5 gap-4 md:gap-6 pb-2 items-start">
              {/* Daily Credits */}
              <div>
                <div className="flex items-center justify-between text-xs font-semibold mb-0.5">
                  <span>Daily Credits</span>
                  <span className="text-muted-foreground">{dailyLeft} / {dailyTot}</span>
                </div>
                <div className="h-2 bg-muted rounded-full overflow-hidden">
                  <div className="h-full bg-[#184777]/70 rounded-full" style={{ width: `${dailyPct}%` }} />
                </div>
              </div>

              {/* Rollover (commented out in your source) */}
              {/*
              <div className="relative rounded-xl border bg-card/60 p-3 min-w-[150px] self-start -mt-2 md:-mt-3">
                <div className="flex items-baseline justify-between">
                  <div className="text-xs font-semibold">Rollover</div>
                  <div className="text-[11px] text-muted-foreground">{eomLabel}</div>
                </div>
                <div className="mt-1 flex items-baseline gap-1">
                  <div className="text-3xl font-bold tabular-nums leading-none">{roll}</div>
                  <div className="text-[11px] text-muted-foreground whitespace-nowrap">/ {bankCap}</div>
                </div>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <button
                      type="button"
                      className="absolute bottom-2 right-2 text-muted-foreground hover:text-foreground"
                      aria-label="What is Rollover?"
                    >
                      <Info className="h-4 w-4" />
                    </button>
                  </TooltipTrigger>
                  <TooltipContent side="top" align="end" className="max-w-[260px] text-xs leading-4">
                    Unused daily credits rollover when you log in. Resets monthly and is capped by your plan.
                  </TooltipContent>
                </Tooltip>
              </div>
              */}

              {/* Rewards */}
              <div className="relative rounded-xl border bg-card/60 p-3 min-w-[150px] self-start -mt-2 md:-mt-3">
                <div className="flex items-baseline justify-between">
                  <div className="text-xs font-semibold">Rewards</div>
                  <div className="text-[11px] text-muted-foreground">Never expires</div>
                </div>
                <div className="mt-1 flex items-baseline gap-1">
                  <div className="text-3xl font-bold tabular-nums leading-none">{rewards}</div>
                </div>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <button
                      type="button"
                      className="absolute bottom-2 right-2 text-muted-foreground hover:text-foreground"
                      aria-label="How to earn Rewards?"
                    >
                      <Info className="h-4 w-4" />
                    </button>
                  </TooltipTrigger>
                  <TooltipContent side="top" align="end" className="max-w-[260px] text-xs leading-4">
                    Earn badges, gain XP, and progress through tiers to receive free credits that never expire.
                  </TooltipContent>
                </Tooltip>
              </div>

              {/* STL Exports */}
              <div className="relative rounded-xl border bg-card/60 p-3 min-w-[150px] self-start -mt-2 md:-mt-3">
                <div className="flex items-baseline justify-between">
                  <div className="text-xs font-semibold">STL Exports</div>
                  <div className="text-[11px] text-muted-foreground">{resetShort(stl?.resetAtISO)}</div>
                </div>
                <div className="mt-1 flex items-baseline gap-1">
                  <div className="text-3xl font-bold tabular-nums leading-none">{stl?.used ?? 0}</div>
                  {stl?.cap != null ? (
                    <div className="text-[11px] text-muted-foreground whitespace-nowrap">/ {stl.cap}</div>
                  ) : (
                    <div className="text-[11px] text-muted-foreground whitespace-nowrap">/ ∞</div>
                  )}
                </div>
              </div>

              {/* STEP Exports */}
              <div className="relative rounded-xl border bg-card/60 p-3 min-w-[150px] self-start -mt-2 md:-mt-3">
                <div className="flex items-baseline justify-between">
                  <div className="text-xs font-semibold">STEP Exports</div>
                  <div className="text-[11px] text-muted-foreground">{resetShort(step?.resetAtISO)}</div>
                </div>
                <div className="mt-1 flex items-baseline gap-1">
                  <div className="text-3xl font-bold tabular-nums leading-none">{step?.used ?? 0}</div>
                  {step?.cap != null ? (
                    <div className="text-[11px] text-muted-foreground whitespace-nowrap">/ {step.cap}</div>
                  ) : (
                    <div className="text-[11px] text-muted-foreground whitespace-nowrap">/ ∞</div>
                  )}
                </div>
              </div>

              {/* New Projects / week */}
              <div className="relative rounded-xl border bg-card/60 p-3 min-w-[150px] self-start -mt-2 md:-mt-3">
                <div className="flex items-baseline justify-between">
                  <div className="text-xs font-semibold">New Projects</div>
                  <div className="text-[11px] text-muted-foreground">{resetShort(proj?.resetAtISO)}</div>
                </div>
                <div className="mt-1 flex items-baseline gap-1">
                  <div className="text-3xl font-bold tabular-nums leading-none">{proj?.used ?? 0}</div>
                  {proj?.cap != null ? (
                    <div className="text-[11px] text-muted-foreground whitespace-nowrap">/ {proj.cap}</div>
                  ) : (
                    <div className="text-[11px] text-muted-foreground whitespace-nowrap">/ ∞</div>
                  )}
                </div>
              </div>
            </div>
          </TooltipProvider>
        </div>
      )}

      {/* Plans (unchanged) */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 pt-6 items-stretch">
        <PlanCard
          title="Free"
          eaPrice={PLAN_META.free.priceEA}
          fullPrice={PLAN_META.free.priceFull}
          showEaBadge={false}
          showFullPrice={false}
          features={[
            "5 daily credits",
            "Up to 50 credits/month",
            "10 STL & 5 STEP exports/month",
          ]}
          ctaLabel={plan === "free" ? "Current Plan" : "Switch to Free"}
          // Prefer using portal to cancel paid subscription cleanly:
          onClick={plan === "free" ? undefined : managePaymentPrefs}
          disabled={plan === "free" || busyPlan !== null}
        />

        <PlanCard
          title="Plus"
          eaPrice={PLAN_META.plus.priceEA}
          fullPrice={PLAN_META.plus.priceFull}
          per="per month"
          features={[
            "15 daily credits",
            "Up to 200 credits/month",
            "20 STL & 10 STEP exports/month",
            "Priority queue",
          ]}
          ctaLabel={
            plan === "plus"
              ? "Current Plan"
              : planRank(plan) < planRank("plus")
              ? "Upgrade to Plus"
              : "Switch to Plus"
          }
          onClick={
            plan === "plus"
              ? undefined
              : planRank(plan) < planRank("plus")
              ? () => startCheckout("plus")     // ✅ upgrade via Stripe Checkout
              : managePaymentPrefs               // ✅ downgrade via portal
          }
          disabled={plan === "plus" || busyPlan !== null}
        />

        <PlanCard
          title="Pro"
          eaPrice={PLAN_META.pro.priceEA}
          fullPrice={PLAN_META.pro.priceFull}
          per="per month"
          popular
          features={[
            "30 daily credits",
            "Up to 500 credits/month",
            "Unlimited STL & STEP exports",
            "Private projects",
            "First access to new features & models",
            "Fast-track queue + priority support",
          ]}
          ctaLabel={plan === "pro" ? "Current Plan" : "Upgrade to Pro"}
          onClick={plan === "pro" ? undefined : () => startCheckout("pro")}  // ✅ upgrade via Stripe
          disabled={plan === "pro" || busyPlan !== null}
        />
      </div>
    </>
  );
}

function PlanCard({
  title,
  eaPrice,
  fullPrice,
  per,
  features,
  ctaLabel,
  onClick,
  disabled,
  extra,
  popular = false,
  showEaBadge = true,
  showFullPrice = true,
}: {
  title: string;
  eaPrice: string;
  fullPrice: string;
  per?: string;
  features: string[];
  ctaLabel: string;
  onClick?: () => void;
  disabled?: boolean;
  extra?: React.ReactNode;
  popular?: boolean;
  showEaBadge?: boolean;
  showFullPrice?: boolean;
}) {
  return (
    <div
      className={[
        "relative h-full overflow-hidden rounded-3xl min-w-0 w-full",
        "bg-[#FFFFFF] text-primary",
        "border border-white/10 shadow-[0_10px_30px_rgba(0,0,0,0.25)]",
        "p-6 sm:p-7 flex flex-col",
        popular ? "ring-2 ring-[#FFCA85]" : "ring-1 ring-white/5",
      ].join(" ")}
    >
      {popular && (
        <div className="pointer-events-none absolute -right-12 bottom-9 -rotate-45">
          <div className="bg-[#FFCA85] text-white text-[12px] font-semibold tracking-wide px-16 py-1.5 shadow-lg">
            Popular
          </div>
        </div>
      )}

      <div className="mb-5">
        <div className="flex items-center justify-between gap-3">
          <h3 className="text-sm font-medium text-primary/80">{title}</h3>
          <span
            className={[
              "h-6 inline-flex items-center text-[11px] px-2.5 rounded-full",
              "border border-black/10 bg-black/[0.03]",
              showEaBadge ? "" : "invisible",
            ].join(" ")}
          >
            Early Access discount
          </span>
        </div>

        <div className="mt-2">
          <div className="flex items-end gap-1">
            <span className="text-4xl sm:text-5xl font-bold leading-none">{eaPrice}</span>
            <span className={["text-sm text-primary/60 mb-1", per ? "" : "invisible"].join(" ")}>
              {per || "per month"}
            </span>
          </div>
          <div className={["mt-1 text-sm text-primary/60 line-through", showFullPrice ? "" : "invisible"].join(" ")}>
            {fullPrice}{per ? ` ${per}` : " per month"}
          </div>
        </div>
      </div>

      <button
        type="button"
        onClick={(e) => {
          e.preventDefault();         // don't submit a surrounding form
          e.stopPropagation();        // don't trigger any parent link/click handlers
          onClick?.();
        }}
        disabled={disabled}
        className={[
          "group mt-1 inline-flex items-center justify-between w-full",
          "rounded-full px-5 py-2.5 text-sm font-semibold",
          disabled
            ? "bg-white/20 text-primary cursor-default"
            : "bg-gradient-to-r from-[#FFFFFF] to-[#D6F3FF] hover:brightness-110",
          "shadow-lg ring-1 ring-black/10 transition",
        ].join(" ")}
      >
        <span>{ctaLabel}</span>
        <span className={[
          "grid place-items-center h-8 w-8 rounded-full",
          "bg-primary/60 text-white group-hover:bg-primary/90",
        ].join(" ")}>
          <Play className="h-3.5 w-3.5" />
        </span>
      </button>

      {extra}

      <ul className="mt-6 space-y-3 text-sm text-primary/85">
        {features.map((f) => (
          <li key={f} className="flex items-start gap-3">
            <CheckCircle2 className="h-4 w-4 mt-[2px] text-[#184777]/80" />
            <span>{f}</span>
          </li>
        ))}
      </ul>

      <div className="mt-auto" />
    </div>
  );
}
