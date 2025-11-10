import { X, AlertTriangle, PiggyBank, Gift, Crown, Coins, Info } from "lucide-react";
import { Button } from "@/components/ui/button";
import { createPortal } from "react-dom";
import logo from "/Makistry.png";
import { useCreditGate } from "@/stores/useCreditGate";
import { api } from "@/lib/api";

function fmtReset(iso?: string) {
  if (!iso) return null;
  try {
    const d = new Date(iso);
    const left = Math.max(0, d.getTime() - Date.now());
    const hrs = Math.floor(left / 3_600_000);
    const mins = Math.floor((left % 3_600_000) / 60_000);
    return `${d.toLocaleString()} • resets in ${hrs}h ${mins}m`;
  } catch {
    return new Date(iso).toLocaleString();
  }
}

function cap(s?: string | null) {
  if (!s) return "";
  return s.slice(0, 1).toUpperCase() + s.slice(1);
}

export function CreditGateModal() {
  const { open, close, limits, level, plan, banks, selected, select, proceed } = useCreditGate();
  if (!open) return null;

  const planName = cap(plan ?? "free");

  const headline =
    level === "daily"
      ? `You've reached the ${planName} plan's daily limit.`
      : `You've reached the ${planName}'s monthly limit`;

  const resetWhen =
    level === "daily" ? fmtReset(limits?.dayResetAtISO) : fmtReset(limits?.monthResetAtISO);

  const goBilling = () => {
    close();
    window.location.href = "/settings?plan=sub#billing";
  };

  const goInfo = () => {
    close();
    window.open("/info/credits", "_blank", "noopener,noreferrer"); // TODO: wire this route when your info page is ready
  };

  const hasRollover = (banks?.rollover ?? 0) > 0;
  const hasRewards = (banks?.rewards ?? 0) > 0;
  const canUseBank = (hasRollover || hasRewards);

  const handleUseBank = async () => {
    if (!selected) return;
    try {
      // Persist which bank to spend from; backend will debit as tokens exceed daily quota.
      await api.post("/account/bank/use", { source: selected }); // "rollover" | "rewards"
    } catch (e) {
      console.error("Failed to activate bank mode:", e);
      return;
    }
    proceed(); // continue the original blocked action
  };

  return createPortal(
    <div className="fixed inset-0 z-[2000] flex items-center justify-center">
      <div className="absolute inset-0 bg-black/50" onClick={close} />
      <div className="relative z-[2001] w-full max-w-md rounded-2xl bg-white p-7 shadow-xl">
        {/* Info (top-left) */}
        <button
          className="absolute left-3 top-3 p-1 text-gray-500 hover:text-gray-700"
          onClick={goInfo}
          aria-label="Learn about credits"
          title="Learn about credits"
        >
          <Info className="h-5 w-5" />
        </button>

        {/* Close (top-right) */}
        <button
          className="absolute right-3 top-3 p-1 text-gray-500 hover:text-gray-700"
          onClick={close}
          aria-label="Close"
          title="Close"
        >
          <X className="h-5 w-5" />
        </button>

        <div className="flex flex-col items-center text-center">
          <img src={logo} alt="Makistry" className="h-10 mb-3" />

          <div className="flex flex-col items-center text-[#031926]">
            <h2 className="text-xl font-semibold">{headline}</h2>
          </div>

          <p className="mt-4 mb-2 text-sm text-[#031926]/80 max-w-sm">
            Use banked credits, upgrade plans, or get credits to continue making!
          </p>

          {/* Bank selection (only when daily is out) */}
          {canUseBank && (
            <>
              <div className="mt-3 grid grid-cols-1 gap-3 w-full">
                {/* Rollover
                <button
                  type="button"
                  onClick={() => hasRollover && select("rollover")}
                  disabled={!hasRollover}
                  className={[
                    "rounded-xl border p-4 text-left",
                    hasRollover ? "hover:bg-amber-50 cursor-pointer" : "opacity-50 cursor-not-allowed",
                    selected === "rollover" ? "border-amber-500 ring-2 ring-amber-200" : "border-gray-200",
                  ].join(" ")}
                >
                  <div className="flex items-center gap-2 font-medium text-[#031926]">
                    <PiggyBank className="h-4 w-4" />
                    Rollover
                  </div>
                  <div className="mt-1 text-sm text-[#031926]/70">
                    {banks?.rollover ?? 0} credits
                  </div>
                </button> */}

                {/* Tier rewards */}
                <button
                  type="button"
                  onClick={() => hasRewards && select("rewards")}
                  disabled={!hasRewards}
                  className={[
                    "rounded-xl border p-4 text-left",
                    hasRewards ? "hover:bg-blue-50 cursor-pointer" : "opacity-50 cursor-not-allowed",
                    selected === "rewards" ? "border-blue-500 ring-2 ring-blue-200" : "border-gray-200",
                  ].join(" ")}
                >
                  <div className="flex items-center gap-2 font-medium text-[#031926]">
                    <Gift className="h-4 w-4" />
                    Tier rewards
                  </div>
                  <div className="mt-1 text-sm text-[#031926]/70">
                    {banks?.rewards ?? 0} credits
                  </div>
                </button>
              </div>

              <Button
                variant="outline"
                className="mt-4 w-full bg-white hover:bg-white/80 text-black shadow-sm"
                disabled={!selected}
                onClick={handleUseBank}
              >
                {selected
                  ? `Use ${selected === "rollover" ? "Rollover" : "Tier rewards"} credits`
                  : "Select a credit source"}
              </Button>
            </>
          )}

          {/* Upsell actions */}
          <div className="mt-6 grid grid-cols-2 gap-3 w-full">
            <Button
              className="w-full bg-[#FFCA85] hover:bg-[#FFCA85]/90 text-[#031926]"
              onClick={goBilling}
            >
              <Crown className="w-4 h-4 mr-1" />
              Upgrade
            </Button>
            <Button
              className="w-full bg-[#031926] hover:bg-[#031926]/80 text-white"
              onClick={goBilling}
            >
              <Coins className="w-4 h-4 mr-1" />
              Get credits
            </Button>
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
}
