// src/lib/plans.ts
import type { Plan } from "@/lib/api/account";

export const PLAN_META: Record<Plan, {
  label: string;
  daily: number;
  monthlyCap: number;
  bankCap: number;
  priceEA: string;   // early-access label
  priceFull: string;
}> = {
  free: { label: "Free", daily: 5,  monthlyCap: 50,  bankCap: 10, priceEA: "$0",  priceFull: "$0"  },
  plus: { label: "Plus", daily: 15, monthlyCap: 200, bankCap: 30, priceEA: "$10", priceFull: "$25" },
  pro:  { label: "Pro",  daily: 30, monthlyCap: 500, bankCap: 50, priceEA: "$25", priceFull: "$40" },
};

export const planRank = (p: Plan) => ({ free: 0, plus: 1, pro: 2 }[p]);
export const isPaid   = (p: Plan) => p !== "free";
export const isPro    = (p: Plan) => p === "pro";
