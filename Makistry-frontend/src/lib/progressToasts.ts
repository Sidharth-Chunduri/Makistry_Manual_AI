import { toast } from "sonner";
import type { ProgressAward, ProgressSnapshot } from "@/lib/api/account";

const TIER_NAMES = {
  apprentice: "Apprentice",
  maker: "Maker", 
  engineer: "Engineer",
  innovator: "Innovator",
  inventor: "Inventor"
} as const;

const BADGE_NAMES = {
  designs: "Designer",
  remixes: "Remixer",
  likes: "Popular",
  shares: "Influencer", 
  exports: "Builder"
} as const;

function addStreakLine(msgs: string[], oldSnap: ProgressSnapshot | null, newSnap: ProgressSnapshot) {
  const oldDays = oldSnap?.streak?.days ?? 0;
  const newDays = newSnap?.streak?.days ?? 0;
  if (newDays > oldDays) {
    msgs.push(`🔥 ${newDays}-day streak!`);
  }
}

export function toastFromAward(
  award: ProgressAward, 
  oldSnapshot: ProgressSnapshot | null, 
  newSnapshot: ProgressSnapshot
) {
  if (award.skipped === "duplicate") return;

  const messages: string[] = [];

  if (award.awardedXp > 0) {
    const mult = award.multiplier > 1 ? ` (${award.multiplier}x streak bonus!)` : "";
    messages.push(`+${award.awardedXp} XP${mult}`);
  }
  if (award.badgeLevel > 0) {
    messages.push(`Badge upgraded to level ${award.badgeLevel}!`);
  }
  if (oldSnapshot && oldSnapshot.tier !== newSnapshot.tier) {
    const tierName = TIER_NAMES[newSnapshot.tier] || newSnapshot.tier;
    messages.push(`🎉 Promoted to ${tierName} tier!`);
    if (award.tierCreditDelta > 0) messages.push(`+${award.tierCreditDelta} free credits earned!`);
  }

  addStreakLine(messages, oldSnapshot, newSnapshot);

  if (messages.length > 0) toast.success(messages.join(" "));
}

export function toastFromCategoryAward(
  category: keyof typeof BADGE_NAMES,
  award: ProgressAward,
  oldSnapshot: ProgressSnapshot | null,
  newSnapshot: ProgressSnapshot
) {
  if (award.skipped === "duplicate") return;

  const messages: string[] = [];

  if (award.awardedXp > 0) {
    const mult = award.multiplier > 1 ? ` (${award.multiplier}x streak bonus!)` : "";
    messages.push(`+${award.awardedXp} XP${mult}`);
  }
  if (award.badgeLevel > 0) {
    const badgeName = BADGE_NAMES[category] || category;
    messages.push(`${badgeName} badge upgraded to level ${award.badgeLevel}!`);
  }
  if (oldSnapshot && oldSnapshot.tier !== newSnapshot.tier) {
    const tierName = TIER_NAMES[newSnapshot.tier] || newSnapshot.tier;
    messages.push(`🎉 Promoted to ${tierName} tier!`);
    if (award.tierCreditDelta > 0) messages.push(`+${award.tierCreditDelta} free credits earned!`);
  }

  addStreakLine(messages, oldSnapshot, newSnapshot);

  if (messages.length > 0) toast.success(messages.join(" "));
}
