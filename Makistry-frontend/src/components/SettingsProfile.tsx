// SettingsProfile.tsx
import { useEffect, useRef, useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { updateMe, deleteAccount } from "@/lib/api/account";
import { useQueryClient } from "@tanstack/react-query";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Trophy, Flame, Box, Repeat, Heart, Share2, Download } from "lucide-react";
import { useAccount } from "@/hooks/useAccount";
import { UserAvatar } from "@/components/UserAvatar"; // ✅ use shared avatar

type Tier = "apprentice" | "maker" | "engineer" | "innovator" | "inventor";

// Subtle, tier-tinted pill colors to match the avatar scheme
const TIER_PILL: Record<Tier, string> = {
  apprentice: "bg-slate-100 text-slate-800",
  maker:      "bg-amber-100 text-amber-900",
  engineer:   "bg-zinc-100 text-zinc-800",
  innovator:  "bg-yellow-100 text-yellow-900",
  inventor:   "bg-sky-100 text-indigo-800",
};

const BADGE_META = {
  designs: { label: "Designs", Icon: Box,    currentLine: (n: number) => `${n} ${n === 1 ? "design" : "designs"} created` },
  remixes: { label: "Remixes", Icon: Repeat, currentLine: (n: number) => `${n} ${n === 1 ? "remix" : "remixes"} made` },
  likes:   { label: "Likes",   Icon: Heart,  currentLine: (n: number) => `${n} ${n === 1 ? "project" : "projects"} liked` },
  shares:  { label: "Shares",  Icon: Share2, currentLine: (n: number) => `${n} ${n === 1 ? "share" : "shares"} opened` },
  exports: { label: "Exports", Icon: Download,currentLine: (n: number) => `${n} ${n === 1 ? "export" : "exports"} completed` },
} as const;

const cap10 = (s: string) => (s ?? "").slice(0, 10);

export function SettingsProfile() {
  const { user, logout } = useAuth();
  const [saving, setSaving] = useState(false);
  const [dangerBusy, setDangerBusy] = useState(false);

  const [username, setUsername] = useState("");
  const [email, setEmail]       = useState(user?.email ?? "");

  const { data: me, isLoading: loading } = useAccount();
  const qc = useQueryClient();
  const isComposingRef = useRef(false);

  // Track last saved username to avoid redundant writes
  const lastSavedRef = useRef<string>("");
  const inflightRef = useRef<Promise<void> | null>(null);

  useEffect(() => {
    if (!me) return;
    const local = (me.email || user?.email || "").split("@")[0] || "";
    const uname = cap10(me.username || local);
    setUsername(uname);
    setEmail(me.email || user?.email || "");
    lastSavedRef.current = uname; // seed last saved
  }, [me, user?.email]);

  async function flushSave() {
    const next = cap10((username || "").trim());
    if (!next || next === lastSavedRef.current) return;

    setSaving(true);
    try {
      if (inflightRef.current) await inflightRef.current;

      inflightRef.current = updateMe({ username: next }).then(() => {
        qc.setQueryData(["me"], (prev: any) =>
          prev ? { ...prev, username: next } : prev
        );
        lastSavedRef.current = next;
      }).finally(() => {
        inflightRef.current = null;
      });

      await inflightRef.current;
    } finally {
      setSaving(false);
    }
  }

  const handleBlur = () => { void flushSave(); };

  useEffect(() => {
    return () => { void flushSave(); };
  }, []);

  async function onDelete() {
    if (!confirm("This permanently deletes your account and projects. Continue?")) return;
    setDangerBusy(true);
    try {
      await deleteAccount();
      logout();
      window.location.href = "/";
    } finally {
      setDangerBusy(false);
    }
  }

  if (loading) return <p className="text-sm text-muted-foreground">Loading…</p>;

  const xp        = Number(me?.xp ?? 0);
  const nextTier  = me?.nextTierXp ?? null;
  const tier      = (me?.tier ?? "apprentice") as Tier;
  const tierLabel = String(me?.tier ?? "apprentice").toUpperCase();
  const xpPct     = nextTier ? Math.min(100, Math.round((xp / nextTier) * 100)) : 100;
  const streakDays= Number(me?.streak?.days ?? 0);
  const mult      = Number(me?.streak?.multiplier ?? 1);
  const badges    = (me?.badges ?? {}) as Record<
    keyof typeof BADGE_META,
    { count: number; level: number }
  >;

  return (
    <div className="space-y-8 gap-6">
      {/* Avatar + basics */}
      <div className="flex items-center gap-4">
        <div className="relative">
          <UserAvatar
            username={username}
            src={me?.photoUrl || undefined}
            tier={tier}
            size={64}                     // h-16 w-16
            className="rounded-xl"        // keep square-ish profile look
            alt={`${username} avatar`}
          />
        </div>

        {/* Profile fields */}
        <div className="grid grid-cols-1 gap-8 pl-6 sm:grid-cols-2">
          <div>
            <Label>Username</Label>
            <Input
              value={username}
              maxLength={10}
              onChange={(e) => setUsername(cap10(e.target.value))}
              onBlur={handleBlur}
              onCompositionStart={() => (isComposingRef.current = true)}
              onCompositionEnd={() => (isComposingRef.current = false)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !isComposingRef.current) {
                  e.preventDefault();
                  (e.currentTarget as HTMLInputElement).blur();
                }
              }}
              placeholder="max 10 characters"
            />
            <div className="mt-1 text-xs text-muted-foreground flex items-center gap-2">
              <span>{username.length}/10</span>
              <span className="opacity-60">
                {saving ? "Saving…" : (lastSavedRef.current === cap10(username) ? "Saved" : "")}
              </span>
            </div>
          </div>
          <div>
            <Label>Email</Label>
            <Input value={email} disabled />
          </div>
        </div>
      </div>

      {/* Account overview */}
      <div className="rounded-2xl border bg-card p-4 shadow-sm pb-6">
        <div className="flex items-center gap-2 mb-3">
          <Trophy className="w-4 h-4" />
          <p className="text-base font-medium">Progress</p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-[1.2fr_1px_1.8fr] gap-8">
          <div>
            {/* Tier label pill matches avatar color family */}
            <div className="mb-2">
              <span
                className={[
                  "inline-block px-2 py-0.5 rounded-full text-xs font-semibold",
                  TIER_PILL[tier],
                ].join(" ")}
              >
                {tierLabel}
              </span>
            </div>

            <div className="text-sm font-medium">{xp} XP</div>
            <div className="mt-2 h-2 bg-muted rounded-full overflow-hidden">
              <div
                className="h-full rounded-full"
                style={{
                  width: `${xpPct}%`,
                  backgroundImage:
                    "linear-gradient(90deg, #FFCA85 0%, #FFD7A6 45%, #FFF3E4 50%, #FFD7A6 55%, #FFCA85 100%)",
                  boxShadow:
                    "0 0 6px rgba(255,202,133,0.6), inset 0 0 4px rgba(255,255,255,0.4)",
                }}
              />
            </div>
            <div className="mt-1 text-xs text-muted-foreground">
              {nextTier ? `${Math.max(0, nextTier - xp)} XP to next tier` : "Top tier"}
            </div>

            <div className="mt-4 flex items-center justify-between rounded-xl border px-3 py-2">
              <div className="flex items-center gap-2">
                <Flame className="w-4 h-4" />
                <span className="text-sm font-medium">{streakDays}-day streak</span>
              </div>
              <div className="text-xs text-muted-foreground">x{mult} XP</div>
            </div>
          </div>

          <div className="hidden lg:block bg-border" />

          <div className="grid grid-cols-2 sm:grid-cols-3 gap-6">
            {(Object.keys(BADGE_META) as Array<keyof typeof BADGE_META>).map((key) => {
              const { label, Icon, currentLine } = BADGE_META[key];
              const count = badges?.[key]?.count ?? 0;
              const level = Math.max(0, Math.min(4, badges?.[key]?.level ?? 0));
              return (
                <div key={key} className="flex flex-col items-center text-center gap-1">
                  <div
                    className={[
                      "h-12 w-12 grid place-items-center rounded-full",
                      level >= 4
                        ? "bg-gradient-to-br from-cyan-200 to-sky-600 text-white"
                        : level >= 3
                        ? "bg-gradient-to-br from-yellow-200 to-yellow-500 text-white"
                        : level >= 2
                        ? "bg-gradient-to-br from-slate-200 to-slate-500 text-white"
                        : level >= 1
                        ? "bg-gradient-to-br from-amber-300 to-orange-600 text-white"
                        : "bg-white text-foreground border",
                    ].join(" ")}
                  >
                    <Icon className="w-6 h-6" />
                  </div>
                  <div className="text-sm font-medium">{label}</div>
                  <div className="text-xs text-muted-foreground">{currentLine(count)}</div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Footer without Save button */}
      <div className="flex items-center justify-between">
        <div className="space-y-2">
          <p className="text-sm font-medium">Danger zone</p>
          <Button variant="destructive" onClick={onDelete} disabled={dangerBusy}>
            {dangerBusy ? "Deleting…" : "Delete account"}
          </Button>
        </div>
      </div>
    </div>
  );
}
