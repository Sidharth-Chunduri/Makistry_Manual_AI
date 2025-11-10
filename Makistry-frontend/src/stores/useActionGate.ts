import { create } from "zustand";
import type { Plan } from "@/lib/api/account";

export type ActionName = "export_stl" | "export_step" | "project_create" | "private_projects";

export interface ActionLimits {
  used: number;           // how many used in the window
  cap: number | null;     // null = Unlimited (shouldn’t 402)
  resetAtISO: string;     // when the counter resets
}

type State = {
  open: boolean;
  plan: Plan | null;
  action: ActionName | null;
  limits: ActionLimits | null;
  gateFor?: "stl" | "step" | "brainstorm" | null;
  openGate: (p: { plan: Plan; action: ActionName; limits?: ActionLimits | null; gateFor?: State["gateFor"] }) => void;
  close: () => void;
};

export const useActionGate = create<State>((set) => ({
  open: false,
  plan: null,
  action: null,
  limits: null,
  gateFor: null,
  openGate: ({ plan, action, limits, gateFor }) =>
    set({ open: true, plan, action, limits: limits ?? null, gateFor: gateFor ?? null }),
  close: () => set({ open: false }),
}));
