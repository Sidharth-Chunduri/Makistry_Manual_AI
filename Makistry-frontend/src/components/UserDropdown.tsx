// UserDropdown.tsx
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/hooks/useAuth";
import { Settings, Info, Crown, LogOut, ArrowRight, ChevronDown } from "lucide-react";
import { useState, useMemo } from "react";
import { type Plan } from "@/lib/api/account";
import { PLAN_META, isPaid, isPro as isProPlan } from "@/lib/plans";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { useAccount } from "@/hooks/useAccount";
import { UserAvatar } from "@/components/UserAvatar"; // ✅ use the shared avatar

type Tier = "apprentice" | "maker" | "engineer" | "innovator" | "inventor";

export function UserDropdown() {
  const nav = useNavigate();
  const { user, logout } = useAuth();
  const { data: me, isLoading: loading } = useAccount();
  const [bankOpen, setBankOpen] = useState(false);

  if (!user) return null;

  const emailFallback = user.email;
  const usernameFallback = emailFallback.split("@")[0];

  const email    = me?.email ?? emailFallback;
  const username = me?.username ?? usernameFallback;
  const plan: Plan = (me?.plan as Plan) ?? "free";
  const planMeta   = PLAN_META[plan];
  const paid       = isPaid(plan);
  const proBadge   = isProPlan(plan);

  const credits  = me?.creditsLeft ?? 0;
  const dailyTot = me?.dailyQuota ?? planMeta.daily;
  const pct      = Math.min(100, dailyTot ? (credits / dailyTot) * 100 : 0);

  const avatar   = me?.photoUrl || undefined;

  const roll    = me?.bankRollover ?? 0;
  const rewards = me?.bankRewards  ?? me?.creditsBank ?? 0;
  const bankCap = me?.bankCap ?? planMeta.bankCap;
  const bankPct = Math.min(100, bankCap ? (roll / bankCap) * 100 : 0);
  const tier = (me?.tier ?? "apprentice") as Tier;

  const eomLabel = useMemo(() => {
    const iso = me?.bankExpiryISO;
    if (!iso) return "Resets month-end";
    try {
      const d = new Date(iso + "T23:59:59");
      return `Resets ${d.toLocaleDateString(undefined, { month: "short", day: "numeric" })}`;
    } catch { return "Resets month-end"; }
  }, [me?.bankExpiryISO]);

  const AV_SIZE = 28; // matches h-7 w-7

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" className="flex items-center gap-2 rounded-lg px-3 h-10">
          <UserAvatar
            username={username}
            src={avatar}
            tier={tier}
            size={AV_SIZE}
            className="shrink-0"
            alt={`${username} avatar`}
          />
          <span className="hidden sm:inline text-sm font-medium text-foreground/80">
            {username}
          </span>
        </Button>
      </DropdownMenuTrigger>

      <DropdownMenuContent align="end" className="w-72 p-0">
        <div className="px-4 py-3 border-b">
          <div className="flex items-center gap-3">
            <UserAvatar
              username={username}
              src={avatar}
              tier={tier}
              size={AV_SIZE}
              className="shrink-0"
              alt={`${username} avatar`}
            />
            <div className="gap-2">
              <p className="text-sm font-medium leading-none gap-1 flex items-center">
                {username}&apos;s&nbsp;Makerspace
                <span className="ml-2 text-[10px] px-1.5 py-0.5 rounded-full bg-[#184777]/20 text-black">
                  {planMeta.label.toUpperCase()}
                </span>
              </p>
              <p className="text-xs text-muted-foreground">{email}</p>
            </div>
          </div>

          {!paid ? (
            <div className="mt-4">
              <Button
                size="sm"
                className="w-full bg-[#FFCA85] hover:bg-[#FFCA85]/90 text-[#031926]"
                onClick={() => nav("/settings?plan=sub#billing")}
              >
                <Crown className="w-4 h-4 mr-2" />
                Upgrade
              </Button>
            </div>
          ) : (
            <div className="mt-4">
              <Button
                size="sm"
                variant="secondary"
                className="w-full bg-[#031926]/90 hover:bg-[#031926]/60 text-white"
                onClick={() => nav("/settings?plan=sub#billing")}
              >
                Manage plan
              </Button>
            </div>
          )}

          <div className="mt-4">
            <div className="flex items-center justify-between text-xs font-semibold mb-1">
              <span>Daily Credits</span>
              <span className="text-muted-foreground">{credits} / {dailyTot} left</span>
            </div>

            <div className="h-2 bg-muted rounded-full overflow-hidden">
              <div
                className="h-full bg-[#184777]/70 rounded-full"
                style={{ width: `${pct}%` }}
              />
            </div>

            <div className="mt-2 mb-1 flex items-center justify-between gap-2">
              <button
                type="button"
                onClick={() => setBankOpen((v) => !v)}
                className="inline-flex items-center gap-1 text-[13px] font-semibold text-primary/90 hover:text-primary/70"
                aria-expanded={bankOpen}
                aria-controls="bank-details"
              >
                Bank
                <ChevronDown className={`w-4 h-4 transition-transform ${bankOpen ? "rotate-180" : ""}`} />
              </button>

              <Button
                variant="ghost"
                size="sm"
                className="h-auto px-0 text-xs font-medium hover:bg-transparent underline-offset-4 hover:underline"
                onClick={() => nav("/settings#billing")}
              >
                Get more credits
                <ArrowRight className="w-4 h-4 ml-1" />
              </Button>
            </div>

            {bankOpen && (
              <TooltipProvider delayDuration={150}>
                <div id="bank-details-dd" className="mt-2 mb-1 space-y-2">
                  <div className="relative rounded-xl border bg-card/60 p-3">
                    <div className="flex items-baseline justify-between">
                      <div className="text-xs font-semibold">Tier Rewards</div>
                      <div className="text-[11px] text-muted-foreground">Never expires</div>
                    </div>
                    <div className="mt-1 flex items-baseline gap-1">
                      <div className="text-3xl font-bold tabular-nums">{rewards}</div>
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
                      <TooltipContent side="right" align="end" className="max-w-[260px] text-xs leading-4">
                        Earn badges, gain XP, and move up tiers to earn free credits as progress rewards.
                      </TooltipContent>
                    </Tooltip>
                  </div>
                </div>
              </TooltipProvider>
            )}
          </div>
        </div>

        <div className="mt-4 mb-4 mx-4 flex gap-2">
          <Button
            size="sm"
            variant="secondary"
            className="flex-1 bg-[#031926]/60 hover:bg-[#031926]/90 text-white"
            onClick={() => nav("/settings")}
          >
            <Settings className="w-4 h-4 mr-1" />
            Settings
          </Button>
          <Button
            asChild
            size="sm"
            variant="secondary"
            className="flex-1 bg-[#031926]/60 hover:bg-[#031926]/90 text-white"
          >
            <a href="https://makistry.com/info" target="_blank" rel="noopener noreferrer">
              <Info className="w-4 h-4 mr-1" />
              Help
            </a>
          </Button>
        </div>

        <DropdownMenuSeparator />

        <div className="px-1 py-1 text-sm text-muted-foreground">
          <DropdownMenuItem onSelect={logout}>
            <LogOut className="w-4 h-4 ml-2 mr-2" />
            Sign&nbsp;out
          </DropdownMenuItem>
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
