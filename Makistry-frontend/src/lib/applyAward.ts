import { useProgressStore } from "@/stores/useProgressStore";
import type { ProgressAward, ProgressSnapshot } from "@/lib/api/account";
import { toastFromCategoryAward } from "@/lib/progressToasts";

export type AwardCategory = "designs" | "remixes" | "likes" | "shares" | "exports";

export function applyAward(category: AwardCategory, award: ProgressAward, snapshot: ProgressSnapshot) {
  const { snapshot: old } = useProgressStore.getState();
  // category-aware (nicer copy)
  toastFromCategoryAward(category, award, old ?? null, snapshot);
  useProgressStore.getState().setSnapshot(snapshot);
}