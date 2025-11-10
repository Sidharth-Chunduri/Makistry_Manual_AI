// src/stores/useProgressStore.ts
import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { ProgressSnapshot } from "@/lib/api/account";
import { refreshProgress } from "@/lib/api/account";
// add this import at top
import type { AccountMe } from "@/lib/api/account";

type State = {
  snapshot: ProgressSnapshot | null;
  userId: string | null;                              // ⬅ track owner of snapshot
  setSnapshot: (s: ProgressSnapshot, userId?: string|null) => void;
  setFromMe: (me: AccountMe) => void;                // ⬅ convenience mapper
  refresh: () => Promise<void>;
  initialize: (expectedUserId?: string|null) => Promise<void>;
};

export const useProgressStore = create<State>()(
  persist(
    (set, get) => ({
      snapshot: null,
      userId: null,
      setSnapshot: (s, userId = null) => {
        set({ snapshot: s, userId });
      },
      setFromMe: (me) => {
        const s: ProgressSnapshot = {
          xp: me.xp ?? 0,
          tier: me.tier ?? "apprentice",
          creditsBank: me.creditsBank ?? 0,
          nextTierXp: typeof me.nextTierXp === "number" ? me.nextTierXp : null,
          streak: me.streak ?? { days: 0, best: 0, multiplier: 1, last: null },
          badges: me.badges ?? {},
        };
        set({ snapshot: s, userId: me.userID ?? null });
      },
      refresh: async () => {
        try {
          const me = await (await import("@/lib/api/account")).getMe();
          get().setFromMe(me);
        } catch (error) {
          console.error("Failed to refresh progress:", error);
        }
      },
      initialize: async (expectedUserId) => {
        const currentUser = get().userId;
        // If store empty or belongs to a different user → fetch fresh
        if (!currentUser || (expectedUserId && currentUser !== expectedUserId)) {
          try {
            const me = await (await import("@/lib/api/account")).getMe();
            get().setFromMe(me);
          } catch (error) {
            // silent – not logged in yet, etc.
          }
        }
      },
    }),
    {
      name: "progress-store",
      partialize: (state) => ({ snapshot: state.snapshot, userId: state.userId }),
    }
  )
);
