// src/components/TopBar.tsx
import { useEffect, useRef, useState, useMemo } from "react";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import {
  ChevronDown,
  History,
  Sidebar,
  Download,
  Share2,
  Crown,
  Trophy,
  Home,
  Pencil,
  Settings as SettingsIcon,
  Info,
  ArrowRight,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import { saveAs } from "file-saver";
import { fetchBrainstormPDF, fetchCad, fetchStep, pollStepStatus } from "@/lib/api/artifacts";
import { useNavigate } from "react-router-dom";
import { ShareDropdown } from "@/components/ShareDropdown";
import { api } from "@/lib/api";
import { useProgressStore } from "@/stores/useProgressStore";
import { ProgressDialog } from "@/components/ProgressDialog";
import { getMe, type AccountMe, type Plan } from "@/lib/api/account";
import { PLAN_META } from "@/lib/plans";
import { useAuth } from "@/hooks/useAuth";
import { Input } from "@/components/ui/input";
import { useAccount } from "@/hooks/useAccount";
import { ActionGateModal } from "@/components/ActionGateModal";
import { useActionGate } from "@/stores/useActionGate";
import type { ActionLimits } from "@/stores/useActionGate";

interface TopBarProps {
  onToggleVersionHistory: () => void;
  onToggleSidebar: () => void;
  isSidebarVisible: boolean;
  isVersionHistoryVisible: boolean;
  tokensPercentage: number;
  projectName: string | null;
  projectId: string | null;
  brainVersion?: number | null;
  cadVersion?: number | null;
  cadCodeVersion?: number | null;
  onProjectRename?: (newTitle: string) => void;
}

export function TopBar({
  onToggleVersionHistory,
  onToggleSidebar,
  isSidebarVisible,
  isVersionHistoryVisible,
  tokensPercentage,
  projectName,
  projectId,
  brainVersion,
  cadVersion,
  cadCodeVersion,
  onProjectRename,
}: TopBarProps) {
  const nav = useNavigate();
  const goDashboardSafe = () => {
    const to = "/";
    sessionStorage.setItem("projects:refreshOnNextDashboard", "1");
    // If we're already on the dashboard, force a refresh to guarantee exit.
    if (window.location.pathname === to) {
      window.location.assign(to);
      return;
    }

    // Defer until after the dropdown finishes closing to avoid focus/timing issues.
    requestAnimationFrame(() => {
      try {
        nav(to);
        // Belt-and-suspenders: if SPA nav didn’t change the path, hard redirect.
        requestAnimationFrame(() => {
          if (window.location.pathname !== to) window.location.assign(to);
        });
      } catch {
        window.location.assign(to);
      }
    });
  };

  const [shareUrl, setShareUrl] = useState<string | null>(null);
  const message = "Check out this design I made on Makistry!";
  const [showShare, setShowShare] = useState<boolean>(false);
  const [showProgress, setShowProgress] = useState(false);
  const { refresh } = useProgressStore();
  const { user } = useAuth();

  // Inline rename state
  const [isRenaming, setIsRenaming] = useState(false);
  const [draftTitle, setDraftTitle] = useState(projectName ?? "Untitled Project");
  const renameRef = useRef<HTMLInputElement | null>(null);

  const openActionGate = useActionGate((s) => s.openGate);

  function maybeOpenActionGateFromError(err: any, fallbackPlan: any, which: "export_stl" | "export_step") {
    // Axios-style: err.response?.data; fetch-style: body text in err.message
    const detail = err?.response?.data?.detail ?? err?.response?.data ?? null;
    if (detail?.error === "limit_reached_action" && detail?.action === which) {
      openActionGate({
        plan: (fallbackPlan as any) ?? "free",
        action: which,
        limits: detail.limits as ActionLimits,
        gateFor: which === "export_stl" ? "stl" : "step",
      });
      return true;
    }
    return false;
  }

  // sync local draft when prop changes (unless actively editing)
  useEffect(() => {
    if (!isRenaming) setDraftTitle(projectName ?? "Untitled Project");
  }, [projectName, isRenaming]);

  const { data: me } = useAccount();

  async function handleExportBrainstorm() {
    if (!projectId) return;
    try {
      const pdfBlob = await fetchBrainstormPDF(projectId, brainVersion ?? null);
      saveAs(pdfBlob, `${projectName} brainstorm-Makistry.pdf`);
    } catch (err) {
      console.error("Failed to export brainstorm:", err);
    }
  }

  async function handleExportSTL() {
    if (!projectId) return;
    try {
      const result = await fetchCad(projectId, cadVersion ?? null, true);
      if (!result?.blobUrl) return;
      const resp = await fetch(result.blobUrl);
      if (!resp.ok) return;
      const blob = await resp.blob();
      saveAs(blob, `${projectName}-Makistry.stl`);
      try {
        await refresh();
      } catch {}
    } catch (err: any) {
      if (maybeOpenActionGateFromError(err, me?.plan, "export_stl")) return;
      console.error("Failed to export STL:", err);
    }
  }

  // ---------- inline rename ----------
  function beginInlineRename() {
    if (!projectId) return;
    setDraftTitle(projectName ?? "Untitled Project");
    setIsRenaming(true);
    // Focus after dropdown closes
    setTimeout(() => renameRef.current?.focus(), 0);
  }

  async function commitInlineRename() {
    if (!projectId) {
      setIsRenaming(false);
      return;
    }
    const next = (draftTitle || "").trim();
    if (!next || next === (projectName ?? "")) {
      setIsRenaming(false);
      setDraftTitle(projectName ?? "Untitled Project");
      return;
    }
    try {
      // Use the same route as your Projects grid
      await api.patch(`/projects/${projectId}/title`, { title: next });
      onProjectRename?.(next);
    } catch (err) {
      console.error("Rename failed:", err);
      setDraftTitle(projectName ?? "Untitled Project"); // rollback text
    } finally {
      setIsRenaming(false);
    }
  }
  // -----------------------------------

  const emailFallback = user?.email ?? "";
  const usernameFallback = emailFallback ? emailFallback.split("@")[0] : "Maker";
  const username = me?.username ?? usernameFallback;
  const plan: Plan = (me?.plan as Plan) ?? "free";
  const meta = PLAN_META[plan];
  const credits = me?.creditsLeft ?? 0;
  const dailyTot = me?.dailyQuota ?? meta.daily;
  const dailyPct = Math.min(100, dailyTot ? (credits / dailyTot) * 100 : 0);
  const bank = me?.creditsBank ?? 0;
  const upgradeLabel =
    plan === "free" ? "Upgrade" : plan === "plus" ? "Upgrade to Pro" : "Manage plan";
  const goManagePlan = () => nav("/settings?plan=sub#billing");

  const roll   = me?.bankRollover ?? 0;                   // monthly rollover
  const rewards= me?.bankRewards  ?? me?.creditsBank ?? 0;// lifetime rewards
  const bankCap= me?.bankCap ?? meta.bankCap;

  const bankPct = Math.min(100, bankCap ? (roll / bankCap) * 100 : 0);

  const eomLabel = useMemo(() => {
    const iso = me?.bankExpiryISO;
    if (!iso) return "Resets month-end";
    try {
      const d = new Date(iso + "T23:59:59");
      return `Resets ${d.toLocaleDateString(undefined, { month: "short", day: "numeric" })}`;
    } catch { return "Resets month-end"; }
  }, [me?.bankExpiryISO]);

  const [bankOpen, setBankOpen] = useState(false);


  const handleShare = async () => {
    if (!projectId) return;
    try {
      if (shareUrl) {
        setShowShare(true);
        return;
      }
      const { data } = await api.post<{ url: string }>(`/share/${projectId}`);
      const newShareUrl = data.url;
      setShareUrl(newShareUrl);
      if (navigator.clipboard) {
        try {
          await navigator.clipboard.writeText(newShareUrl);
        } catch {}
      }
      setShowShare(true);
    } catch (error) {
      console.error("Failed to create share link:", error);
    }
  };

  return (
    <div className="h-16 bg-background border-b border-border flex items-center justify-between px-6">
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <img src="/Makistry.png" alt="Makistry" className="h-10 w-auto" />
        </div>

        <div className="flex items-center gap-1">
          {!isRenaming ? (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="sm" className="hover:bg-primary/5">
                  <span className="hidden sm:inline text-base">{projectName || "Untitled"}</span>
                  <ChevronDown className="w-6 h-6" />
                </Button>
              </DropdownMenuTrigger>

              {/* Workspace menu */}
              <DropdownMenuContent align="start" className="w-80 p-0">
                <div className="px-1 py-1">
                  <DropdownMenuItem asChild>
                    <button
                      type="button"
                      onClick={goDashboardSafe}
                      className="w-full flex items-center"
                    >
                      <Home className="w-4 h-4 mr-2" />
                      Go to dashboard
                    </button>
                  </DropdownMenuItem>
                </div>

                <div className="px-4 pt-1 pb-2 border-b">
                  <p className="text-xs text-muted-foreground flex items-center gap-2">
                    {username}&apos;s Makerspace
                    <span className="ml-2 text-[10px] px-1.5 py-0.5 rounded-full bg-[#184777]/20 text-black">
                      {meta.label.toUpperCase()}
                    </span>
                  </p>
                </div>

                {/* Credits */}
                <div className="px-4 pt-3">
                  <div className="flex items-center justify-between text-xs font-semibold mb-1">
                    <span>Daily Credits</span>
                    <span className="text-muted-foreground">
                      {dailyTot ? `${credits}/${dailyTot} left` : `${credits}`}
                    </span>
                  </div>
                  <div className="h-2 bg-muted rounded-full overflow-hidden">
                    <div className="h-full bg-[#184777]/80 rounded-full" style={{ width: `${dailyPct}%` }} />
                  </div>

                  {/* Row: Bank (left) + Get more credits (right) */}
                  <div className="mt-3 flex items-center justify-between gap-2 mb-3">
                    <button
                      type="button"
                      onClick={() => setBankOpen((v) => !v)}
                      className="inline-flex items-center gap-1 text-[13px] font-semibold text-primary/90 hover:text-primary/80"
                      aria-expanded={bankOpen}
                      aria-controls="bank-details-dd"
                    >
                      Bank
                      <ChevronDown className={`w-4 h-4 transition-transform ${bankOpen ? "rotate-180" : ""}`} />
                    </button>

                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-auto text-xs font-medium hover:bg-transparent underline-offset-4 hover:underline"
                      onClick={() => nav("/settings#billing")}
                    >
                      Get More Credits
                      <ArrowRight className="w-4 h-4 ml-1" />
                    </Button>
                  </div>


                  {bankOpen && (
                    <TooltipProvider delayDuration={30}>
                      <div id="bank-details" className="mt-2 mb-2 space-y-2">
                        {/* Rollover card
                        <div className="relative rounded-xl border bg-card/60 p-3">
                          <div className="flex items-baseline justify-between">
                            <div className="text-xs font-semibold">Rollover</div>
                            <div className="text-[11px] text-muted-foreground">{eomLabel}</div>
                          </div>

                          <div className="mt-1 flex items-baseline gap-1">
                            <div className="text-3xl font-bold tabular-nums">{roll}</div>
                            <div className="text-xs text-muted-foreground">/ {bankCap}</div>
                          </div>

                          <Tooltip>
                            <TooltipTrigger asChild>
                              <button
                                type="button"
                                className="absolute bottom-2 right-2 text-muted-foreground hover:text-foreground"
                                aria-label="What is Rollover?"
                              >
                                <Info className="h-4 w-4" />
                              </button>
                            </TooltipTrigger>
                            <TooltipContent side="right" align="end" className="max-w-[240px] text-xs leading-4">
                              Unused daily credits rollover when you log in.
                            </TooltipContent>
                          </Tooltip>
                        </div> */}

                        {/* Rewards card */}
                        <div className="relative rounded-xl border bg-card/60 p-3">
                          <div className="flex items-baseline justify-between">
                            <div className="text-xs font-semibold">Tier Rewards</div>
                            <div className="text-[11px] text-muted-foreground">Never expires</div>
                          </div>

                          <div className="mt-1 flex items-baseline gap-1">
                            <div className="text-3xl font-bold tabular-nums">{rewards}</div>
                          </div>

                          <Tooltip>
                            <TooltipTrigger asChild>
                              <button
                                type="button"
                                className="absolute bottom-2 right-2 text-muted-foreground hover:text-foreground"
                                aria-label="How to earn Rewards?"
                              >
                                <Info className="h-4 w-4" />
                              </button>
                            </TooltipTrigger>
                            <TooltipContent side="right" align="end" className="max-w-[260px] text-xs leading-4">
                              Earn badges, gain XP, and move up tiers to earn free credits as progress rewards. 
                            </TooltipContent>
                          </Tooltip>
                        </div>
                      </div>
                    </TooltipProvider>
                  )}

                </div>

                <DropdownMenuSeparator />

                <div className="mt-3 mb-3 mx-4 grid grid-cols-2 gap-2">
                  <Button
                    size="sm"
                    variant="secondary"
                    className="bg-[#031926]/60 hover:bg-[#031926]/90 text-white"
                    onClick={() => nav("/settings")}
                  >
                    <SettingsIcon className="w-4 h-4 mr-1" />
                    Settings
                  </Button>
                  <Button
                    asChild
                    size="sm"
                    variant="secondary"
                    className="flex-1 bg-[#031926]/60 hover:bg-[#031926]/90 text-white"
                  >
                    <a href="https://makistry.com/info" target="_blank" rel="noopener noreferrer">
                      <Info className="w-4 h-4 mr-1" />
                      Help
                    </a>
                  </Button>
                </div>

                <DropdownMenuSeparator />

                {/* Rename → switch to inline input */}
                <div className="px-1 py-1">
                  <DropdownMenuItem
                    onSelect={(e) => {
                      e.preventDefault();
                      beginInlineRename();
                    }}
                  >
                    <Pencil className="w-4 h-4 mr-2" />
                    Rename project
                  </DropdownMenuItem>
                </div>
              </DropdownMenuContent>
            </DropdownMenu>
          ) : (
            <Input
              ref={renameRef}
              value={draftTitle}
              onChange={(e) => setDraftTitle(e.target.value)}
              onBlur={commitInlineRename}
              onKeyDown={(e) => {
                if (e.key === "Enter") commitInlineRename();
                if (e.key === "Escape") {
                  setIsRenaming(false);
                  setDraftTitle(projectName ?? "Untitled Project");
                }
              }}
              placeholder="Untitled Project"
              className="h-8 w-[220px] sm:w-[300px]"
              aria-label="Rename project"
            />
          )}
        </div>

        {/* Mid: Version + Sidebar Toggles */}
        <div
          className="absolute top-4 -translate-x-full flex items-center gap-2 z-10"
          style={{ left: "35%" }}
        >
          <Button
            variant="ghost"
            size="sm"
            onClick={onToggleVersionHistory}
            className={isVersionHistoryVisible ? "bg-[accent]" : ""}
            title="Version History"
          >
            <History className="w-8 h-8" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={onToggleSidebar}
            className={!isSidebarVisible ? "bg-accent" : ""}
            title={isSidebarVisible ? "Hide Chat" : "Show Chat"}
          >
            <Sidebar className="w-8 h-8" />
          </Button>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <Button
          variant="outline"
          size="sm"
          className="bg-[#FFCA85] hover:bg-[#FFCA85]/80 hover:text-black text-black shadow-sm border-black/10"
          onClick={goManagePlan}
        >
          <Crown className="w-4 h-4 mr-1" />
          {upgradeLabel}
        </Button>

        <Button
          variant="outline"
          size="sm"
          className="hover:bg-[#031926]/10 shadow-sm"
          onClick={() => setShowProgress(true)}
        >
          <Trophy className="w-4 h-4" />
          Progress
        </Button>
        <ProgressDialog open={showProgress} onOpenChange={setShowProgress} />
        <ActionGateModal />

        {projectId &&
          (shareUrl ? (
            <ShareDropdown
              url={shareUrl}
              message={message}
              projectId={projectId}
              open={showShare}
              onOpenChange={setShowShare}
            />
          ) : (
            <Button
              variant="outline"
              size="sm"
              className="hover:bg-[#031926]/10 shadow-sm"
              onClick={handleShare}
            >
              <Share2 className="w-4 h-4" />
              Share
            </Button>
          ))}

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="outline"
              size="sm"
              className="bg-[#031926] text-white hover:bg-[#184777]/80 hover:text-white shadow-sm"
            >
              <Download className="w-4 h-4 mr-1" />
              Export
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent>
            <DropdownMenuItem onClick={handleExportBrainstorm}>
              Brainstorm - PDF
            </DropdownMenuItem>
            <DropdownMenuItem onClick={handleExportSTL}>
              STL - 3D printing
            </DropdownMenuItem>
            <DropdownMenuItem
              onClick={async () => {
                if (!projectId) return;
                try {
                  // Kick off (idempotent)
                  const maybeUrl = await fetchStep(projectId, cadCodeVersion ?? null);

                  // If ready immediately, download; else poll status
                  const url = maybeUrl || (await pollStepStatus(projectId, cadCodeVersion ?? null));
                  const resp = await fetch(url);
                  saveAs(await resp.blob(), `${projectName ?? "Makistry"} CAD.step`);
                  try { await refresh(); } catch {}
                } catch (err: any) {
                  if (maybeOpenActionGateFromError(err, me?.plan, "export_step")) return;
                  console.error("STEP export failed:", err);
                }
              }}
            >
              STEP - CAD editing
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </div>
  );
}
