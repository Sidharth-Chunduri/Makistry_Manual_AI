import { create } from "zustand";
import type { Plan } from "@/lib/api/account";

export type Limits = {
  dailyQuota: number;
  creditsLeft: number;
  creditsToday: number;
  monthlyCap: number;
  monthlyUsed: number;
  monthlyRemaining: number;
  dayResetAtISO?: string;
  monthResetAtISO?: string;
};

type Level = "daily" | "monthly";
type PartialLimits = Partial<Limits>;
type BankChoice = "rollover" | "rewards" | null;

function normalize(l: PartialLimits): Limits {
  const dailyQuota        = l.dailyQuota        ?? 0;
  const creditsLeft       = l.creditsLeft       ?? 0;
  const creditsToday      = l.creditsToday      ?? Math.max(0, dailyQuota - creditsLeft);
  const monthlyCap        = l.monthlyCap        ?? 0;
  const monthlyUsed       = l.monthlyUsed       ?? 0;
  const monthlyRemaining  = l.monthlyRemaining  ?? Math.max(0, monthlyCap - monthlyUsed);
  return {
    dailyQuota,
    creditsLeft,
    creditsToday,
    monthlyCap,
    monthlyUsed,
    monthlyRemaining,
    dayResetAtISO: l.dayResetAtISO ?? nextLocalMidnightISO(),
    monthResetAtISO: l.monthResetAtISO ?? nextMonthStartISO(),
  };
}

function inferLevel(l: Limits): Level {
  if (l.monthlyRemaining <= 0) return "monthly";
  if (l.creditsLeft <= 0) return "daily";
  return "daily";
}

function nextLocalMidnightISO() {
  const d = new Date();
  d.setHours(24, 0, 0, 0); // next local midnight
  return d.toISOString();
}

function nextMonthStartISO() {
  const now = new Date();
  const d = new Date(now.getFullYear(), now.getMonth() + 1, 1, 0, 0, 0, 0);
  return d.toISOString();
}

type GateFor = "brainstorm" | "generate" | "edit" | "chat";

interface OpenArgs {
  limits?: PartialLimits;
  plan?: Plan;
  banks?: { rollover: number; rewards: number };
  gateFor?: GateFor;
  onContinue?: (choice: Exclude<BankChoice, null> | null) => void;
}

interface State {
  open: boolean;
  limits: Limits | null;
  level: Level | null;
  plan: Plan | null;
  banks: { rollover: number; rewards: number } | null;
  selected: Exclude<BankChoice, null> | null;
  gateFor: GateFor | null;
  onContinue: ((choice: Exclude<BankChoice, null> | null) => void) | null;

  openGate: (args?: OpenArgs) => void;
  close: () => void;
  select: (c: Exclude<BankChoice, null>) => void;
  proceed: () => void;
}

export const useCreditGate = create<State>((set, get) => ({
  open: false,
  limits: null,
  level: null,
  plan: null,
  banks: null,
  selected: null,
  gateFor: null,
  onContinue: null,

  openGate: (args) => {
    const limits = normalize(args?.limits ?? {});
    const level = inferLevel(limits);
    set({
      open: true,
      limits,
      level,
      plan: args?.plan ?? null,
      banks: args?.banks ?? null,
      selected: null,
      gateFor: args?.gateFor ?? null,
      onContinue: args?.onContinue ?? null,
    });
  },
  close: () =>
    set({
      open: false,
      limits: null,
      level: null,
      plan: null,
      banks: null,
      selected: null,
      gateFor: null,
      onContinue: null,
    }),
  select: (c) => set({ selected: c }),
  proceed: () => {
    const { onContinue, selected } = get();
    // Close before continuing to feel snappy
    set({ open: false });
    onContinue?.(selected ?? null);
    // Clear state
    set({
      limits: null,
      level: null,
      plan: null,
      banks: null,
      selected: null,
      gateFor: null,
      onContinue: null,
    });
  },
}));

export const openCreditGate = (args?: OpenArgs) => useCreditGate.getState().openGate(args);
export const closeCreditGate = () => useCreditGate.getState().close();
