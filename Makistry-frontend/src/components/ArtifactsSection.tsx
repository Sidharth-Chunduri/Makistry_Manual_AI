// src/components/ArtifactsSection.tsx
import { useEffect, useState, useRef } from "react";
import { Lightbulb, Box } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import BrainstormView from "./artifacts/BrainstormView";
import DesignView from "./artifacts/DesignView";
import { FeatureTreeSidebar } from "@/components/FeatureTreeSidebar";
import type { BrainstormJSON } from "@/hooks/useBrainstorm";
import { useGenerateDesign } from "@/hooks/useGenerateDesign";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchBrainstorm, fetchCad } from "@/lib/api/artifacts";
import { useChatStore } from "@/contexts/ChatStore";
import { FeaturesScroller } from "@/components/FeaturesScroller";
import { LoadingDots } from "@/components/LoadingDots";
import { useAccount } from "@/hooks/useAccount";
import { useCreditGate } from "@/stores/useCreditGate";
import { isInFlight, setInFlight, clearInFlight } from "@/lib/inflight";

type TabKey = "brainstorm" | "design";

interface ArtifactsSectionProps {
  isExpanded: boolean;
  projectId: string | null;
  brainstorm: BrainstormJSON | null;
  refreshToken?: number;
  brainVersion: number | null;
  cadVersion: number | null;
  externalLock?: boolean;
  setBusyPhase?: (p: "idle"|"brainstorm"|"generate"|"chat") => void;
  brainstorming?: boolean;
  busy?: boolean;
  onBundleUpdate?: () => void;
  onDesignReady?: (info?: { version?: number; blobUrl?: string }) => void;
  readOnly?: boolean;
  forceDesignOpen?: boolean;
}

export function ArtifactsSection({
  isExpanded,
  projectId,
  brainstorm: bootstrapBrainstorm,
  refreshToken = 0,
  brainVersion,
  cadVersion,
  externalLock = false,
  setBusyPhase,
  brainstorming = false,
  busy = false,
  onBundleUpdate,
  onDesignReady,
}: ArtifactsSectionProps) {
  const [mainTab, setMainTab] = useState<TabKey>("brainstorm");
  const [isFeatureTreeVisible, setIsFeatureTreeVisible] = useState(false);
  const prevProjectId = useRef<string | null>(null);
  const genDesign = useGenerateDesign();
  const queryClient = useQueryClient();

  const { appendAssistant } = useChatStore(projectId);

  type BrainstormAPIResp = { brainstorm: BrainstormJSON };

  const announcedReadyRef = useRef(false);

  // local blob until first cad query resolves (covers immediate generate response)
  const [blobUrlManual, setBlobUrlManual] = useState<string | null>(null);

  const designAlreadySaved = cadVersion != null;

  const [hasEverGenerated, setHasEverGenerated] = useState<boolean>(designAlreadySaved);
  const [designEnabled, setDesignEnabled] = useState<boolean>(designAlreadySaved);

  // In-flight is sticky (sessionStorage) so re-mounts won't regress UI
  const inflight = projectId ? isInFlight("codegen", projectId) : false;
  const generating = genDesign.isPending || inflight;

  const { data: me } = useAccount();
  const openGate = useCreditGate((s) => s.openGate);

  const lastAppliedCadVerRef = useRef<number | null>(cadVersion ?? null);

  const originKey = projectId ? `codegen-origin:${projectId}` : null;
  const getOrigin = () => (originKey ? sessionStorage.getItem(originKey) : null);

  // ───────── Fetch latest brainstorm ─────────
  const {
    data: brainData,
    isFetching: isFetchingBrain,
  } = useQuery({
    queryKey: ["brainstorm", projectId, brainVersion, refreshToken] as const,
    queryFn: async (): Promise<{ brainstorm: BrainstormJSON; version?: number }> => {
      const r = await fetchBrainstorm(projectId!, brainVersion ?? undefined);
      // r.brainstorm can be unknown → coerce to BrainstormJSON (your view already guards/coerces fields)
      return {
        brainstorm: (r as any).brainstorm as BrainstormJSON,
        version: (r as any).version,
      };
    },
    enabled: !!projectId && brainVersion != null,
    staleTime: 5 * 60 * 1000,
    refetchOnWindowFocus: false,
  });

  /* ───────── Fetch latest CAD blob ───────── */
  const {
    data: cadData,
    isFetching: isFetchingCad,
  } = useQuery({
    queryKey: ["cad", projectId, cadVersion, refreshToken],
    queryFn: () => fetchCad(projectId!, cadVersion ?? undefined),
    enabled: !!projectId && cadVersion != null,
    staleTime: 24 * 60 * 60 * 1000,
    gcTime: 25 * 60 * 60 * 1000,
    refetchOnWindowFocus: false,
  });

  /* ───────── Poll until a blobUrl is actually available ───────── */
  // make sure this line is above the cadPoll block:
  const blobUrl = cadData?.blobUrl ?? blobUrlManual;

  const shouldPoll = !!projectId && inflight;

  const cadPoll = useQuery({
    queryKey: ["cad-poll", projectId],
    queryFn: () => fetchCad(projectId!, undefined), // latest slot
    enabled: shouldPoll,
    refetchInterval: inflight ? 2000 : 8000,
    refetchIntervalInBackground: true,
    refetchOnWindowFocus: false,
  });

  // v5: side-effects go in useEffect (no onSuccess)
  useEffect(() => {
    const d = cadPoll.data as { blobUrl?: string; version?: number } | undefined;
    if (!projectId || !d?.blobUrl || d.version == null) return;
    // Only react when the server reports a *new* design version
    if (lastAppliedCadVerRef.current === d.version) return;
    lastAppliedCadVerRef.current = d.version;

    // We detected the STL from polling → switch UI to finished state
    setBlobUrlManual(d.blobUrl);
    setHasEverGenerated(true);
    setDesignEnabled(true);

    // ✅ Only force Design tab if this was a "Generate Design" run (sticky inflight)
    if (inflight || (cadVersion != null && d.version && d.version !== cadVersion)) {
      setMainTab("design");
    }

    const origin = getOrigin();
    onDesignReady?.({ version: d.version, blobUrl: d.blobUrl });

    onBundleUpdate?.();
    queryClient.invalidateQueries({ queryKey: ["versions", projectId] });
    queryClient.invalidateQueries({ queryKey: ["cad", projectId] });
    clearInFlight("codegen", projectId); // stop spinner now that blob exists
  }, [cadPoll.data, projectId, inflight, cadVersion, queryClient, onBundleUpdate]);

  useEffect(() => {
    if (cadVersion != null) lastAppliedCadVerRef.current = cadVersion;
  }, [cadVersion]);

  /* ───────── Derived state ───────── */
  const brainstorm: BrainstormJSON | null =
    brainData?.brainstorm ?? bootstrapBrainstorm ?? null;

  // enable Design tab whenever a CAD version exists or we're inflight
  const showDesignTab = designEnabled || inflight;

  // keep flags in sync when caller switches versions
  useEffect(() => {
    if (cadVersion != null) {
      setHasEverGenerated(true);
      setDesignEnabled(true);
    }
  }, [cadVersion]);

  // When the project changes, reset local flags derived from versions
  useEffect(() => {
    if (prevProjectId.current !== (projectId ?? null)) {
      const hasDesign = cadVersion != null;
      setHasEverGenerated(cadVersion != null);
      setDesignEnabled(cadVersion != null);
      setBlobUrlManual(null);
      setMainTab(hasDesign ? "design" : "brainstorm");
      announcedReadyRef.current = false;
      prevProjectId.current = projectId ?? null;
    }
  }, [projectId, cadVersion]);

  useEffect(() => {
    if (hasEverGenerated) setDesignEnabled(true);
  }, [hasEverGenerated]);

  useEffect(() => {
    if (generating) setBusyPhase?.("generate");
    else setBusyPhase?.("idle");
  }, [generating, setBusyPhase]);

  /* ───────── Generate Design ───────── */
  const handleGenerate = async () => {
    if (!projectId) return;

    const dailyLeft   = me?.creditsLeft ?? 0;
    const dailyQuota  = me?.dailyQuota ?? 0;
    const creditsToday = me?.creditsToday ?? Math.max(0, dailyQuota - dailyLeft);

    const monthlyCap  = me?.monthlyCreditsCap ?? 0;
    const monthlyUsed = me?.monthlyCredits ?? 0;
    const monthlyRemaining = Math.max(0, monthlyCap - monthlyUsed);

    const isDailyOut   = dailyLeft <= 0;
    const isMonthlyOut = monthlyCap > 0 && monthlyRemaining <= 0;

    const kickOff = async () => {
      try {
        announcedReadyRef.current = false;
        setHasEverGenerated(true);
        setDesignEnabled(true);
        setMainTab("design");

        // Sticky immediately in case React remounts or other API calls happen
        if (originKey) sessionStorage.setItem(originKey, "generate");
        setInFlight("codegen", projectId);

        const data = await genDesign.mutateAsync({ project_id: projectId });
        setBlobUrlManual(data.blob_url ?? null);

        queryClient.invalidateQueries({ queryKey: ["cad", projectId] });
        onBundleUpdate?.();
      } catch (e) {
        // onError handler in the mutation manages sticky state for 409 etc.
        // eslint-disable-next-line no-console
        console.error("Generate design error", e);
        if (originKey) sessionStorage.removeItem(originKey);
        clearInFlight("codegen", projectId);
      } finally {
        setBusyPhase?.("idle");
      }
    };

    if (isDailyOut || isMonthlyOut) {
      openGate({
        plan: me?.plan,
        limits: {
          dailyQuota,
          creditsLeft: dailyLeft,
          creditsToday,
          monthlyCap,
          monthlyUsed,
          monthlyRemaining,
        },
        banks: {
          rollover: me?.bankRollover ?? 0,
          rewards: (me?.bankRewards ?? me?.creditsBank ?? 0) || 0,
        },
        gateFor: "generate",
        onContinue: kickOff,
      });
      return;
    }

    // Normal path (has credits)
    await kickOff();
  };

  const showBrainstormAnim = !brainstorm;

  const renderBrainstormGenerating = () => (
    <div className="h-full w-full flex flex-col items-center justify-center gap-6 px-6 text-center">
      <h3 className="text-xl font-semibold text-[#031926]">Exploring ideas...</h3>
      <p className="max-w-md text-sm text-[#031926]/80">
        Defining geometries, components, and features for your design.
      </p>
      <FeaturesScroller />
      <LoadingDots />
    </div>
  );

  const renderDesignGenerating = () => (
    <div className="h-full w-full flex flex-col items-center justify-center gap-6 px-6 text-center">
      <h3 className="text-xl font-semibold text-[#031926]">Making your design...</h3>
      <p className="max-w-md text-sm text-[#031926]/80">
        Converting your brainstorm to a CAD model!
      </p>
      <FeaturesScroller />
      <LoadingDots />
    </div>
  );

  /* ───────── Panels ───────── */
  const renderMainPanel = () => {
    switch (mainTab) {
      case "brainstorm":
        return (
          <div className="h-full w-full relative">
            {showBrainstormAnim ? (
              renderBrainstormGenerating()
            )  : (
              <>
                {isFetchingBrain && (
                  <div className="pointer-events-none absolute inset-0 flex items-center justify-center text-xs text-muted-foreground">
                    Updating…
                  </div>
                )}
                <BrainstormView brainstorm={brainstorm} />
              </>
            )}
          </div>
        );
      case "design": {
        const hasBlob = !!blobUrl;
        const waitingForBlob = !hasBlob && (cadVersion != null || inflight);
        const showFullScreenSpinner = !hasBlob && (generating || waitingForBlob);
        return (
          <div className="h-full w-full relative">
            {showFullScreenSpinner ? (
              renderDesignGenerating()
            ) : hasBlob ? (
              <>
                <DesignView
                  blobUrl={blobUrl!}
                  projectId={projectId!}
                  cadVersion={(cadVersion ?? 0)}
                />
              </>
            ) : null}
          </div>
        );
      }
      default:
        return null;
    }
  };

  /* ───────── JSX ───────── */
  return (
    <div
      className={`${isExpanded ? "w-full" : "w-[65%]"} bg-primary-light flex min-h-full relative`}
    >
      {/* Main content area */}
      <div className="flex-1 flex flex-col min-h-full">
        <Tabs value={mainTab} onValueChange={(v) => setMainTab(v as TabKey)}>
          <div className="w-full flex justify-center mt-4 mb-5">
            <TabsList
              className="grid grid-cols-2 m-4 mb-5 flex-shrink-0"
              style={{ width: "calc(100% / 2 * 1.5)" }}
            >
              <TabsTrigger value="brainstorm" className="text-sm px-3">
                <Lightbulb className="w-4 h-4 mr-1" /> Brainstorm
              </TabsTrigger>

              {showDesignTab ? (
                <TabsTrigger value="design" className="text-sm px-3">
                  <Box className="w-6 h-6 mr-1" /> Design
                </TabsTrigger>
              ) : (
                <Button
                  onClick={handleGenerate}
                  className="bg-cta hover:bg-cta/90 text-cta-foreground text-sm px-3 h-auto py-2"
                  disabled={busy || generating || !projectId }
                >
                  <Box className="w-6 h-6 mr-1" />
                  {generating ? "Generating…" : "Generate Design"}
                </Button>
              )}
            </TabsList>
          </div>
        </Tabs>

        {/* Active panel */}
        <div className="flex-1 px-4 pb-4 overflow-hidden">{renderMainPanel()}</div>
      </div>

      {/* Feature Tree Sidebar - only show when design tab is available */}
      {showDesignTab && (
        <FeatureTreeSidebar
          projectId={projectId}
          isVisible={isFeatureTreeVisible}
          onToggle={() => setIsFeatureTreeVisible(!isFeatureTreeVisible)}
          onRegenerationSuccess={() => {
            // Invalidate all relevant queries to trigger a refresh
            queryClient.invalidateQueries({ queryKey: ["cad", projectId] });
            queryClient.invalidateQueries({ queryKey: ["versions", projectId] });
            // Also call the original onBundleUpdate if it exists
            onBundleUpdate?.();
          }}
        />
      )}
    </div>
  );
}
