// errors.ts
import type { ActionName, ActionLimits } from "@/stores/useActionGate";

/** 402 when credits (daily/monthly) are exhausted */
export class CreditLimitError extends Error {
  limits: any;
  constructor(message: string, limits: any) {
    super(message);
    this.name = "CreditLimitError";
    this.limits = limits;
  }
}


/** 402 when an action limit (STL/STEP/project) is reached */
export class ActionLimitError extends Error {
  action: ActionName;
  limits: ActionLimits;
  constructor(message: string, action: ActionName, limits: ActionLimits) {
    super(message);
    this.name = "ActionLimitError";
    this.action = action;
    this.limits = limits;
  }
}

/** Type guard helpers (optional) */
export function isActionLimitError(e: unknown): e is ActionLimitError {
  return !!e && (e as any).name === "ActionLimitError";
}
export function isCreditLimitError(e: unknown): e is CreditLimitError {
  return !!e && (e as any).name === "CreditLimitError";
}