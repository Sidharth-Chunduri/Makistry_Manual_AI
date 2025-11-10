// src/components/ProgressDialog.tsx
import { useEffect, useMemo } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { useNavigate } from "react-router-dom";
import { getMe } from "@/lib/api/account";
import { Trophy, Flame, Box, Repeat, Heart, Share2, Download, Info } from "lucide-react";
import { useProgressStore } from "@/stores/useProgressStore";

/* --- Badge meta & thresholds (mirror backend) --- */
const BADGE_META = {
  designs: { label: "Designs", Icon: Box, unit: "designs", currentLine: (n: number) => `${n} ${n === 1 ? "design" : "designs"} created` },
  remixes: { label: "Remixes", Icon: Repeat, unit: "remixes", currentLine: (n: number) => `${n} ${n === 1 ? "remix" : "remixes"} made` },
  likes:   { label: "Likes",   Icon: Heart,  unit: "projects", currentLine: (n: number) => `${n} ${n === 1 ? "project" : "projects"} liked` }, // ← you-like count
  shares:  { label: "Shares",  Icon: Share2, unit: "shares",  currentLine: (n: number) => `${n} ${n === 1 ? "share" : "shares"} opened` },
  exports: { label: "Exports", Icon: Download, unit: "exports", currentLine: (n: number) => `${n} ${n === 1 ? "export" : "exports"} completed` },
} as const;

const COUNT_THRESHOLDS = {
  designs: [1, 5, 20, 50],
  remixes: [1, 5, 15, 30],
  likes:   [10, 50, 100, 500],
  shares:  [1, 5, 15, 30],
  exports: [1, 5, 15, 50],
} as const;

const XP_BY_LEVEL = [100, 500, 2500, 5000]; // for levels 1..4
const NEXT_TIER_CAPS = [500, 2000, 10000, 50000];

function coinClass(level: number) {
  switch (level) {
    case 1:  return "bg-gradient-to-br from-amber-300 to-orange-600 text-white shadow ring-2 ring-amber-100";
    case 2:  return "bg-gradient-to-br from-slate-200 to-slate-500 text-white shadow ring-2 ring-slate-100";
    case 3:  return "bg-gradient-to-br from-yellow-200 to-yellow-500 text-white shadow ring-2 ring-yellow-100";
    case 4:  return "bg-gradient-to-br from-cyan-200 to-sky-600 text-white shadow ring-2 ring-cyan-100";
    default: return "bg-white text-foreground border";
  }
}

// Pretty rounding for "XP to next tier": always round **down** to a nice step
function prettyRemaining(n: number): number {
  if (n >= 1000) return Math.floor(n / 100) * 100; // 2,147 -> 2,100
  if (n >= 100)  return Math.floor(n / 50) * 50;   // 201 -> 200, 149 -> 100
  return Math.floor(n / 10) * 10;                  // 27 -> 20
}

export function ProgressDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const nav = useNavigate();
  const { snapshot, setFromMe } = useProgressStore();

  // Fetch once on open (no polling)
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    (async () => {
      try {
        const me = await getMe(); // /account/me
        if (!cancelled) setFromMe(me);
      } catch (e) {
        console.warn("Progress refresh failed", e);
      }
    })();
    return () => { cancelled = true; };
  }, [open, setFromMe]);

  // 🧠 Use the store as the single source of truth
  const me = snapshot;
  const isLoading = open && !me;

  const xp = Number(me?.xp ?? 0);
  const tier = String(me?.tier ?? "apprentice").toUpperCase();
  const apiNext = typeof me?.nextTierXp === "number" ? me.nextTierXp : null;

  const localNext = useMemo(
    () => NEXT_TIER_CAPS.find((cap) => xp < cap) ?? null,
    [xp]
  );
  const nextCap = apiNext ?? localNext;
  const isTopTier = nextCap === null;

  const rawToNext = !isTopTier ? Math.max(0, (nextCap as number) - xp) : 0;
  const prettyToNext = !isTopTier ? prettyRemaining(rawToNext) : 0;

  // Progress % stays exact (don’t pretty-round the bar length)
  const pct = useMemo(() => {
    if (isTopTier) return 100;
    const cap = nextCap as number;
    const p = Math.round((Math.min(xp, cap) / cap) * 100);
    return Math.max(0, Math.min(100, p));
  }, [xp, isTopTier, nextCap]);

  const streakDays = Number(me?.streak?.days ?? 0);
  const mult = Number(me?.streak?.multiplier ?? 1);

  const badges = (me?.badges ?? {}) as Record<
    keyof typeof BADGE_META,
    { count: number; level: number }
  >;

  const topRow: (keyof typeof BADGE_META)[] = ["designs", "remixes"];
  const bottomRow: (keyof typeof BADGE_META)[] = ["likes", "shares", "exports"];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-5xl w-[92vw] max-h-[85vh] overflow-y-auto p-0">
        <DialogHeader className="p-6 pb-3">
          <DialogTitle className="text-xl font-semibold flex items-center gap-2">
            <Trophy className="w-5 h-5" />
            Progress
          </DialogTitle>
          <DialogDescription className="mt-2 text-sm text-muted-foreground">
            Earn badges to gain XP and climb tiers to get free credits—maintain your daily streak for XP boosts!
          </DialogDescription>
        </DialogHeader>

        {isLoading ? (
          <div className="px-6 pb-6 text-sm text-muted-foreground">
            Loading progress…
          </div>
        ) : (
          <div className="px-6 pb-6">
            <div className="grid grid-cols-1 md:grid-cols-[1fr_1px_1.6fr] gap-10">
              {/* LEFT: Tier + XP + Streak */}
              <div className="rounded-2xl bg-card p-5">
                <div className="mb-4">
                  <span className="inline-block px-2 py-0.5 rounded-full text-xs bg-amber-100 text-amber-900">
                    {tier}
                  </span>
                </div>

                <div className="flex items-baseline justify-between">
                  <p className="text-sm font-medium">{xp} XP</p>
                </div>

                {/* Shiny FFCA85 progress bar */}
                <div className="mt-2 h-2 bg-muted rounded-full overflow-hidden">
                  <div
                    className="h-full rounded-full"
                    style={{
                      width: `${pct}%`,
                      // warm shiny gradient + soft glow
                      backgroundImage:
                        "linear-gradient(90deg, #FFCA85 0%, #FFD7A6 45%, #FFF3E4 50%, #FFD7A6 55%, #FFCA85 100%)",
                      boxShadow:
                        "0 0 8px rgba(255,202,133,0.7), inset 0 0 6px rgba(255,255,255,0.5)",
                    }}
                  />
                </div>

                <div className="mt-1 text-xs text-muted-foreground">
                  {isTopTier ? "Top tier" : `${prettyToNext} XP to next tier`}
                </div>

                {/* Streak */}
                <div className="mt-6 flex items-center justify-between rounded-xl border px-3 py-2">
                  <div className="flex items-center gap-2">
                    <Flame className="w-4 h-4" />
                    <span className="text-sm font-medium">{streakDays}-day streak</span>
                  </div>
                  <div className="text-xs text-muted-foreground">
                    x{mult} XP
                  </div>
                </div>
              </div>

              {/* Divider */}
              <div className="hidden md:block bg-border" />

              {/* RIGHT: Badges */}
              <div className="md:pl-2">
                <p className="text-sm font-medium mb-4">Badges</p>

                {/* Top row: 2 */}
                <div className="grid grid-cols-2 gap-6 mb-6">
                  {topRow.map((key) => {
                    const { label, Icon, unit, currentLine } = BADGE_META[key];
                    const count = badges?.[key]?.count ?? 0;
                    const level = Math.min(4, Math.max(0, badges?.[key]?.level ?? 0));
                    const thresholds = COUNT_THRESHOLDS[key];
                    const nextIndex = Math.min(level, thresholds.length - 1);
                    const nextCountGoal = thresholds[nextIndex];
                    const remaining = Math.max(0, nextCountGoal - count);
                    const xpReward = XP_BY_LEVEL[Math.max(0, nextIndex)];

                    return (
                      <div key={key} className="flex flex-col items-center text-center gap-1">
                        <div className={`h-14 w-14 grid place-items-center rounded-full ${coinClass(level)}`}>
                          <Icon className="w-7 h-7" />
                        </div>
                        <div className="mt-1 text-sm font-medium">{label}</div>
                        <div className="text-xs text-muted-foreground">{currentLine(count)}</div>
                        <div className="text-xs font-medium">
                          {level >= 4
                            ? "Max level"
                            : `Next: ${remaining} more for +${xpReward} XP`}
                        </div>
                      </div>
                    );
                  })}
                </div>

                {/* Bottom row: 3 */}
                <div className="grid grid-cols-3 gap-6">
                  {bottomRow.map((key) => {
                    const { label, Icon, unit, currentLine } = BADGE_META[key];
                    const count = badges?.[key]?.count ?? 0;
                    const level = Math.min(4, Math.max(0, badges?.[key]?.level ?? 0));
                    const thresholds = COUNT_THRESHOLDS[key];
                    const nextIndex = Math.min(level, thresholds.length - 1);
                    const nextCountGoal = thresholds[nextIndex];
                    const remaining = Math.max(0, nextCountGoal - count);
                    const xpReward = XP_BY_LEVEL[Math.max(0, nextIndex)];

                    return (
                      <div key={key} className="flex flex-col items-center text-center gap-1">
                        <div className={`h-14 w-14 grid place-items-center rounded-full ${coinClass(level)}`}>
                          <Icon className="w-7 h-7" />
                        </div>
                        <div className="mt-1 text-sm font-medium">{label}</div>
                        <div className="text-xs text-muted-foreground">{currentLine(count)}</div>
                        <div className="text-xs font-medium">
                          {level >= 4
                            ? "Max level"
                            : `Next: ${remaining} more for +${xpReward} XP`}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>

            {/* Footer */}
            <div className="mt-8 flex">
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
        )}
      </DialogContent>
    </Dialog>
  );
}
