// src/lib/api/account.ts
import { api } from "@/lib/api";
import { CreditLimitError, ActionLimitError } from "@/lib/errors";

export type Plan = "free" | "plus" | "pro";

export type ActionLimit = {
  used: number;
  cap: number | null;      // null = Unlimited
  resetAtISO: string;      // local ISO reset
};

export interface AccountMe {
  userID: string;
  email: string;
  username?: string;
  photoUrl?: string | null;
  plan: Plan;
  dailyQuota: number;
  creditsLeft: number;
  creditsToday?: number;
  monthlyCredits?: number;       // legacy / current usage
  monthlyCreditsCap?: number;    // from backend (optional)
  bankCap?: number;              // from backend (optional)
  bankRollover?: number;         // NEW
  bankRewards?: number;          // NEW (maps to creditsBank on the server)
  bankExpiryISO?: string;        // NEW (YYYY-MM-DD)

  actionLimits?: {
    month: {
      stl: ActionLimit;
      step: ActionLimit;
    };
    week: {
      projects: ActionLimit;
    };
    features: {
      private_projects: boolean;
    };
  };

  // Progress fields
  xp: number;
  tier: "apprentice" | "maker" | "engineer" | "innovator" | "inventor";
  creditsBank: number;
  nextTierXp: number | null;
  streak: {
    days: number;
    best: number;
    multiplier: number;
    last: string | null;
  };
  badges: Record<string, { count: number; level: number }>;
}

export function authHeaders() {
  const jwt = localStorage.getItem("jwt");
  return jwt ? { Authorization: `Bearer ${jwt}` } : {};
}

// Axios error un-wrapper so we preserve your 402 typed errors.
function unwrap<T>(p: Promise<import("axios").AxiosResponse<T>>): Promise<T> {
  return p.then(r => r.data).catch((err: any) => {
    const res = err?.response;
    if (res?.status === 402) {
      const detail = res.data?.detail ?? res.data;
      if (detail?.error === "credit_limit_reached") {
        throw new CreditLimitError(detail?.message || "Credit limit reached", detail?.limits);
      }
      if (detail?.error === "limit_reached_action") {
        throw new ActionLimitError(detail?.message || "Action limit reached", detail?.action, detail?.limits);
      }
    }
    const text =
      typeof res?.data === "string" ? res.data :
      (res?.data ? JSON.stringify(res.data) : err?.message);
    throw new Error(`${res?.status || ""} ${res?.statusText || ""} ${text?.slice(0, 200) || ""}`.trim());
  });
}

// ---- API calls ----

export async function getMe(): Promise<AccountMe> {
  return unwrap(api.get<AccountMe>("/account/me"));
}

export async function updateMe(body: { username?: string; photoUrl?: string | null }) {
  return unwrap(api.patch<{ ok: true }>("/account/me", body));
}

export async function setPlan(plan: Plan, extras?: { creditsPerMonth?: string }) {
  return unwrap(api.post<{ ok: true; plan: Plan }>("/account/plan", { plan, ...extras }));
}

export async function deleteAccount() {
  return unwrap(api.delete<{ ok: true }>("/account/me"));
}

export async function uploadAvatar(file: File) {
  const form = new FormData();
  form.append("file", file);
  return unwrap(api.post<{ photoUrl: string }>("/account/avatar", form));
}

// Progress types
export type ProgressCategory = "designs" | "remixes" | "likes" | "shares" | "exports";

export interface ProgressAward {
  awardedXp: number;
  multiplier: number;
  newTier: "apprentice" | "maker" | "engineer" | "innovator" | "inventor";
  tierCreditDelta: number;
  badgeLevel: number;
  badgeCount: number;
  skipped?: "duplicate";
}

export interface ProgressSnapshot {
  xp: number;
  tier: "apprentice" | "maker" | "engineer" | "innovator" | "inventor";
  creditsBank: number;
  nextTierXp: number | null;
  streak: {
    days: number;
    best: number;
    multiplier: number;
    last: string | null;
  };
  badges: Record<string, { count: number; level: number }>;
}

export async function refreshProgress(): Promise<ProgressSnapshot> {
  const me = await getMe();
  return {
    xp: me.xp,
    tier: me.tier,
    creditsBank: me.creditsBank,
    nextTierXp: me.nextTierXp,
    streak: me.streak,
    badges: me.badges,
  };
}

export async function recordProgress(opts: {
  category: ProgressCategory;
  amount?: number;
  uniqueKey?: string | null;
}): Promise<{ award: ProgressAward; snapshot: ProgressSnapshot }> {
  return unwrap(
    api.post<{ award: ProgressAward; snapshot: ProgressSnapshot }>("/account/progress", {
      category: opts.category,
      amount: opts.amount ?? 1,
      uniqueKey: opts.uniqueKey ?? null,
    })
  );
}

// ---- Notifications (REST-polling) ---------------------------------

export type NotificationKind =
  | "credit_threshold"
  | "badge_level"
  | "tier_up"
  | "like"
  | "remix"
  | "message"
  | string;

export interface Notif {
  id: string;
  kind: NotificationKind;
  title: string;
  body: string;
  data?: Record<string, unknown>;
  seen: boolean;
  ts?: string | null;        // ISO
  expiresAt?: string | null; // ISO
}

export async function listNotifications(params?: { onlyUnseen?: boolean; limit?: number }): Promise<Notif[]> {
  const only_unseen = params?.onlyUnseen ?? true;
  const limit = params?.limit ?? 50;
  const data = await unwrap(api.get<{ items: Notif[] }>("/account/notifications", {
    params: { only_unseen, limit },
  }));
  return data.items ?? [];
}

export async function markServerNotificationSeen(id: string): Promise<void> {
  await unwrap(api.post<{ ok: true }>(`/account/notifications/${encodeURIComponent(id)}/seen`));
}
