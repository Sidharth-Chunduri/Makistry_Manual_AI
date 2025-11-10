import { useEffect, useState, useCallback, useRef } from "react";
import { TopBar } from "@/components/TopBar";
import { InitialInput } from "@/components/InitialInput";
import { ChatSection } from "@/components/ChatSection";
import { VersionHistory } from "@/components/VersionHistory";
import { ArtifactsSection } from "@/components/ArtifactsSection";
import { useBrainstorm, type BrainstormResp } from "@/hooks/useBrainstorm";
import { useChatStore } from "@/contexts/ChatStore";
import { fetchVersions, fetchBrainstorm, fetchCad } from "@/lib/api/artifacts";
import { useQuery } from "@tanstack/react-query";
import { useSelectedBundle } from "@/contexts/SelectedBundle";
import { useProjects } from "@/hooks/useProjects";
import { useAuth } from "@/hooks/useAuth";
import { useAccount } from "@/hooks/useAccount";
import { CreditLimitError } from "@/lib/errors";
import { useCreditGate } from "@/stores/useCreditGate";

type BusyPhase = "idle" | "brainstorm" | "generate" | "chat";
const RANK: Record<BusyPhase, number> = { idle: 0, chat: 1, brainstorm: 2, generate: 3 };

interface IndexProps {
  existingProjectId?: string;
}

const Index: React.FC<IndexProps> = ({ existingProjectId }) => {
  const [currentStep, setCurrentStep] = useState<"input" | "workspace">("input");
  const [userQuery, setUserQuery] = useState("");
  const [isSidebarVisible, setIsSidebarVisible] = useState(true);
  const [isVersionHistoryVisible, setIsVersionHistoryVisible] = useState(false);
  const [tokensPercentage] = useState(73); // Mock token usage
  const [brainstorm, setBrainstorm] = useState<BrainstormResp | null>(null);
  const brainstormMutation = useBrainstorm();
  const [busyPhaseState, _setBusyPhase] = useState<BusyPhase>("idle");
  const [projectTitle, setProjectTitle] = useState<string | null>(null);
  const { refresh: refreshMe } = useAccount();
  const { user } = useAuth();  
  const openCreditGateUi = useCreditGate((s) => s.openGate);
  const setBusyPhase = (next: BusyPhase) =>
    _setBusyPhase((cur) => {
      if (next === "idle") return "idle";                 // always allow release
      return RANK[cur] >= RANK[next] ? cur : next;        // keep higher-priority phase
    });
  const [pendingWelcome, setPendingWelcome] = useState(false);
  const projectId = existingProjectId ?? brainstorm?.project_id ?? null;
  const { appendAssistant, loadHistory } = useChatStore(projectId);
  // artifacts refresh (bumped by Chat after edits)
  const [artifactsNonce, setArtifactsNonce] = useState(0);
  const refreshArtifacts = () => setArtifactsNonce((n) => n + 1);
  // If true, automatically jump to the newest bundle when artifacts change.
  // If false, respect the user's manual selection ("pinned" view).
  const [autoFollowLatest, setAutoFollowLatest] = useState(true);
  const {
    selected: selectedBundle,
    setBundle: setSelectedBundle,
  } = useSelectedBundle();

  // Tracks if project initially had a CAD (so we don't announce on existing projects).
  const initialHadCadRef = useRef<boolean>(false);
  // Tracks if we've already announced for THIS project during this session.
  const firstDesignAnnouncedRef = useRef<boolean>(false);

  const refreshToNewestBundle = useCallback(async () => {
    if (!projectId) return;
    if (!autoFollowLatest) return;
    const versions = await fetchVersions(projectId);
    if (!versions.length) return;
    const newest = versions[0];
    setSelectedBundle({
      bundle:       newest.version,
      brain_ver:    newest.brain_ver,
      cad_file_ver: newest.cad_file_ver,
      cad_code_ver: newest.cad_code_ver,
    });
  }, [projectId, autoFollowLatest, setSelectedBundle]);

  const versionsQuery = useQuery({
    queryKey: ["versions", projectId],
    queryFn: () => fetchVersions(projectId!),
    enabled: !!projectId,
    staleTime: 1000 * 60 * 10,    // 10 minutes, so duplicate mounts use cache
    refetchOnWindowFocus: false,  // don’t refetch on focus
  });

  const handleSelectBundle = (sel: typeof selectedBundle) => {
    setSelectedBundle(sel);
    setAutoFollowLatest(false); // user explicitly selected a version → pin it
    if (projectId) {
      localStorage.setItem(
        `lastBundle:${projectId}`,
        JSON.stringify(sel)
      );
    }
  };

  useEffect(() => {
    if (busyPhaseState === "idle") refreshMe();
  }, [busyPhaseState, refreshMe]);

  useEffect(() => {
    if (!pendingWelcome) return;
    if (!projectId) return;
    appendAssistant(
      "That sounds like a great project!\n" +
      "I've brainstormed a few ideas to get us started.\n" +
      "You can ask me questions or request changes to any part of the brainstorm in the chat.\n" +
      "Click the 'Generate Design' button to create a 3D CAD model using the brainstorm when you're ready!"
    );
    setPendingWelcome(false);
  }, [pendingWelcome, projectId, appendAssistant]);

  // call at top‐level of component, not inside useEffect!
  const { data: myProjects = [] } = useProjects(!!user, user?.sub ?? null);

  useEffect(() => {
    if (!existingProjectId || !versionsQuery.isSuccess) return;
    setAutoFollowLatest(true); // entering a project: default to following latest
    setBusyPhase("idle");
    setCurrentStep("workspace");

    const versions = versionsQuery.data!;
    const latest   = versions[0] || { version: null, brain_ver: null, cad_file_ver: null };
    const stored   = localStorage.getItem(`lastBundle:${existingProjectId}`);
    const initial = stored
      ? JSON.parse(stored)
      : {
          bundle:      latest.version,
          brain_ver:   latest.brain_ver,
          cad_file_ver:latest.cad_file_ver,
          cad_code_ver: latest.cad_code_ver,
        };

    setSelectedBundle({
      bundle:       initial.bundle      ?? latest.version,
      brain_ver:    initial.brain_ver   ?? latest.brain_ver,
      cad_file_ver: initial.cad_file_ver ?? latest.cad_file_ver,
      cad_code_ver:  initial.cad_code_ver ?? latest.cad_code_ver,
    });

    initialHadCadRef.current = !!(latest?.cad_file_ver);
    firstDesignAnnouncedRef.current = false;

    // ✅ now use the top‐level hook data
    const meta = myProjects.find((p) => p.id === existingProjectId);
    if (meta) setProjectTitle(meta.title);
  // add myProjects to your deps since it comes from a hook
  }, [existingProjectId, versionsQuery.isSuccess, versionsQuery.data, myProjects]);

  // 2) Load chat history exactly once on project load
  useEffect(() => {
    if (!existingProjectId) return;
    loadHistory();
  }, []);

  const handleInitialSubmit = async (query: string) => {
    setUserQuery(query);
    setSelectedBundle({
      bundle: null,
      brain_ver: null,
      cad_file_ver: null,
      cad_code_ver: null,
    });
    initialHadCadRef.current = false;       // brand-new project, no CAD yet
    firstDesignAnnouncedRef.current = false;
    setBusyPhase("brainstorm");
    setCurrentStep("workspace");
    try {
      const data = await brainstormMutation.mutateAsync(query);
      setBrainstorm(data);
      setSelectedBundle({
        bundle:      1,
        brain_ver:   1,
        cad_file_ver: null,
        cad_code_ver: null,
      });
      setPendingWelcome(true);
    } catch (error: any) {
      if (error instanceof CreditLimitError) {
        // previously: openCreditGate(error.limits);
        openCreditGateUi(); // opens the modal; if your store accepts limits, pass them here
        setCurrentStep("input");
        return;
      }
      console.error("Error during brainstorming:", error);
    } finally {
      setBusyPhase("idle");
      // ensure credits reflect the just-finished call
      refreshMe();
    }
  };

  const handleToggleSidebar = () => {
    setIsSidebarVisible((v) => !v);
    if (isVersionHistoryVisible) setIsVersionHistoryVisible(false);
  };

  const handleToggleVersionHistory = () => {
    setIsVersionHistoryVisible((v) => !v);
    if (!isSidebarVisible) setIsSidebarVisible(true);
  };


  if (currentStep === "input") {
    return <InitialInput onSubmit={handleInitialSubmit} />;
  }

  const inputLocked = busyPhaseState !== "idle";

  return (
    <div className="h-screen bg-background flex flex-col overflow-hidden">
      <TopBar
        onToggleVersionHistory={handleToggleVersionHistory}
        onToggleSidebar={handleToggleSidebar}
        isSidebarVisible={isSidebarVisible}
        isVersionHistoryVisible={isVersionHistoryVisible}
        tokensPercentage={tokensPercentage}
        projectName={projectTitle ?? brainstorm?.brainstorm.project_name ?? null}
        projectId={projectId}
        brainVersion={selectedBundle?.brain_ver ?? null}
        cadVersion={selectedBundle?.cad_file_ver ?? null}
        cadCodeVersion={selectedBundle?.cad_code_ver ?? null}
        onProjectRename={(t) => setProjectTitle(t)} 
      />

      <div className="flex-1 flex min-h-0">
        {isVersionHistoryVisible ? (
          <VersionHistory isVisible={isVersionHistoryVisible} projectId={projectId!} current={selectedBundle?.bundle ?? null} onSelect={handleSelectBundle} disabled={busyPhaseState !== "idle"} />
        ) : (
          <ChatSection
            initialQuery={userQuery}
            projectId={projectId}
            isVisible={isSidebarVisible}
            onArtifactChange={() => {
              // a generate/edit finished → follow newest again
              setAutoFollowLatest(true);
              refreshArtifacts();
              refreshToNewestBundle();
            }}
            externalLock={inputLocked}
            setBusyPhase={setBusyPhase}
            cadCodeVersion={selectedBundle?.cad_code_ver ?? null}
            brainstormVersion={selectedBundle?.brain_ver ?? null}
          />
        )}

        <ArtifactsSection
          key={projectId ?? "pending"}
          isExpanded={!isSidebarVisible}
          projectId={projectId}
          brainstorm={brainstorm?.brainstorm ?? null}
          refreshToken={artifactsNonce}
          brainVersion={selectedBundle?.brain_ver ?? null}
          cadVersion={selectedBundle?.cad_file_ver ?? null}
          externalLock={false}
          setBusyPhase={setBusyPhase}
          brainstorming={busyPhaseState === "brainstorm"}
          busy={busyPhaseState !== "idle"}
          onBundleUpdate={refreshToNewestBundle}
          onDesignReady={(info) => {
            const v = info?.version ?? null;
            if (
              !firstDesignAnnouncedRef.current &&
              !initialHadCadRef.current &&
              v === 1
            ) {
              appendAssistant(
                "Your CAD model is ready!\n" +
                "Now you can:\n" +
                "• View and interact with the 3D model.\n" +
                "• Ask questions or request changes to the design and brainstorm in the chat.\n" +
                "• Toggle between the brainstorm and design tabs.\n" +
                "Share or export your design when you're ready."
              );
              firstDesignAnnouncedRef.current = true;
            }
          }}
        />
      </div>
    </div>
  );
};

export default Index;