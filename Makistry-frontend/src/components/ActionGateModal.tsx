// src/components/ActionGateModal.tsx
import { createPortal } from "react-dom";
import { Button } from "@/components/ui/button";
import { X, Info, Crown, Coins, Package, FileArchive, FolderPlus } from "lucide-react";
import logo from "/Makistry.png";
import { useActionGate, type ActionName } from "@/stores/useActionGate";

function cap(s?: string | null) {
  if (!s) return "";
  return s.slice(0, 1).toUpperCase() + s.slice(1);
}

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

export function ActionGateModal() {
  const { open, close, plan, action, limits } = useActionGate();
  if (!open) return null;

  const planName = cap(plan ?? "free");
  const used = limits?.used ?? 0;
  const capVal = limits?.cap ?? null;
  const resetWhen = fmtReset(limits?.resetAtISO);

  type ActionName = "export_stl" | "export_step" | "project_create" | "private_projects";
  const actionName = (action ?? "export_stl") as ActionName;

  // NEW: feature-gate branch for private projects
  const isFeatureGate = actionName === "private_projects";

  // Hide reset label for STEP on Free plan (usage-gate only)
  const isFreeStep = actionName === "export_step" && (plan ?? "free") === "free";

  const pct = capVal ? Math.min(100, (used / capVal) * 100) : 100;

  // Usage gates only; not used for the private-projects feature gate
  const actionMeta: Record<
    "export_stl" | "export_step" | "project_create",
    { label: string; freq: "monthly" | "weekly"; icon: JSX.Element }
  > = {
    export_stl:     { label: "STL exports",  freq: "monthly", icon: <Package className="h-4 w-4" /> },
    export_step:    { label: "STEP exports", freq: "monthly", icon: <FileArchive className="h-4 w-4" /> },
    project_create: { label: "new projects", freq: "weekly",  icon: <FolderPlus className="h-4 w-4" /> },
  };

  const meta = !isFeatureGate
    ? actionMeta[actionName as "export_stl" | "export_step" | "project_create"]
    : null;

  const headline = isFeatureGate
    ? "Upgrade to have private projects"
    : (meta!.freq === "monthly"
        ? `You've reached the ${planName} plan's monthly ${meta!.label} limit.`
        : `You've reached the ${planName} plan's weekly ${meta!.label} limit.`);

  const subcopy = isFeatureGate
    ? "Go Pro to hide projects from the Community feed. You'll still see them under your Projects."
    : (actionName === "project_create"
        ? "Upgrade your plan to create more new projects every week."
        : "Upgrade your plan to raise monthly export caps.");

  const goUpgrade = () => {
    close();
    window.location.href = "/settings?plan=sub#billing";
  };

  const goPayg = () => {
    close();
    window.location.href = "/settings?plan=sub#billing";
  };

  const goInfo = () => {
    close();
    window.open("https://makistry.com/info", "_blank", "noopener,noreferrer");
  };

  return createPortal(
    <div className="fixed inset-0 z-[2000] flex items-center justify-center">
      <div className="absolute inset-0 bg-black/50" onClick={close} />
      <div className="relative z-[2001] w-full max-w-md rounded-2xl bg-white p-7 shadow-xl">
        {/* Info (top-left) */}
        <button
          className="absolute left-3 top-3 p-1 text-gray-500 hover:text-gray-700"
          onClick={goInfo}
          aria-label="Learn more"
          title="Learn more"
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

          <div className="flex items-center gap-2 text-[#031926]">
            <h2 className="text-xl font-semibold">{headline}</h2>
          </div>

          <p className="mt-3 text-sm text-[#031926]/80 max-w-sm">{subcopy}</p>

          {/* Usage card — HIDDEN for feature gate */}
          {!isFeatureGate && (
            <div className="mt-5 w-full rounded-xl border bg-gray-50 p-4 text-left">
              <div className="flex items-center gap-2 font-medium text-[#031926]">
                {meta!.icon}
                <span>Current usage</span>
              </div>

              <div className="mt-2 flex items-baseline gap-2 text-[#031926]">
                <div className="text-3xl font-bold tabular-nums leading-none">{used}</div>
                <div className="text-sm text-[#031926]/70">/ {capVal == null ? "∞" : capVal}</div>
              </div>

              <div className="mt-2 h-2 w-full rounded-full bg-black/10 overflow-hidden">
                <div
                  className="h-full rounded-full bg-[#184777]"
                  style={{ width: `${pct}%`, opacity: capVal ? 0.8 : 0.3 }}
                />
              </div>

              {/* Hide the reset line for STEP on Free */}
              {resetWhen && !isFreeStep && (
                <div className="mt-2 text-xs text-[#031926]/70">
                  Resets: <b>{resetWhen}</b>
                </div>
              )}
            </div>
          )}

          {/* CTAs */}
          <div className="mt-6 grid grid-cols-1 gap-3 w-full">
            <Button
              className="w-full bg-[#FFCA85] hover:bg-[#FFCA85]/90 text-[#031926]"
              onClick={goUpgrade}
            >
              <Crown className="w-4 h-4 mr-1" />
              Upgrade
            </Button>
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
}
