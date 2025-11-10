import { useParams, useNavigate, useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useState, useEffect } from "react";
import { AuthGateModal } from "@/components/AuthGateModal";
import { useAuth } from "@/hooks/useAuth";
import { remixProject } from "@/lib/api/community";
import { ChatSection } from "@/components/ChatSection";
import { ArtifactsSection } from "@/components/ArtifactsSection";
import { Loader2 } from "lucide-react";
import { ShareTopBar } from "@/components/ShareTopBar";

type ChatMsgWire = {
  id?: string;
  isUser?: boolean;
  role?: "user" | "assistant";
  content?: string;
};

interface ShareResp {
  project_id: string;
  title: string | null;
  owner: string | null;                  // userID (kept for compat)
  owner_username?: string | null;        // NEW: preferred display name
  brain_ver: number | null;
  cad_ver: number | null;
  stl_url: string;
  chat: ChatMsgWire[];
}

export default function ShareView() {
  const { slug } = useParams<{ slug: string }>();
  const { data, isLoading, error } = useQuery<ShareResp, Error>({
    queryKey: ["share", slug],
    queryFn: () => api.get<ShareResp>(`/share/${slug}`).then((r) => r.data),
    enabled: !!slug,
    retry: 1,
  });

  const { user } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();

  const [needAuth, setNeedAuth] = useState(false);
  const [isRemixing, setIsRemixing] = useState(false);
  const [isSidebarVisible, setIsSidebarVisible] = useState(true);
  const [isVersionHistoryVisible, setIsVersionHistoryVisible] = useState(false);

  useEffect(() => {
    if (data?.title) {
      document.title = `${data.title} | Makistry`;
    }
  }, [data?.title]);

  // Normalize chat for ChatSection (ensure isUser is correct even for legacy payloads)
  const chatForBootstrap =
    (data?.chat || []).map((m, i) => ({
      id: m.id ?? `m${i}`,
      isUser:
        typeof m.isUser === "boolean"
          ? m.isUser
          : (m.role || "").toLowerCase() === "user",
      content: m.content ?? "",
    })) ?? [];

  const remix = async () => {
    if (!user) {
      // Remember intent so we can finish the remix after auth
      sessionStorage.setItem(
        "pendingRemix",
        JSON.stringify({
          slug,
          project_id: data?.project_id ?? null,
          cad_ver: data?.cad_ver ?? null,
          brain_ver: data?.brain_ver ?? null,
        })
      );
      setNeedAuth(true);
      return;
    }
    if (!data) return;

    setIsRemixing(true);
    try {
      const res = await remixProject(
        data.project_id,
        data.cad_ver,
        data.brain_ver
      );
      nav(`/project/${res.new_project_id}`);
    } catch (err) {
      console.error("Failed to remix project:", err);
    } finally {
      setIsRemixing(false);
    }
  };

  // If user returns authenticated and we have a pending remix for this slug, complete it
  useEffect(() => {
    if (!user || !data || !slug) return;
    const raw = sessionStorage.getItem("pendingRemix");
    if (!raw) return;
    try {
      const pend = JSON.parse(raw);
      if (pend?.slug === slug) {
        sessionStorage.removeItem("pendingRemix");
        (async () => {
          setIsRemixing(true);
          try {
            const res = await remixProject(
              data.project_id,
              data.cad_ver,
              data.brain_ver
            );
            nav(`/project/${res.new_project_id}`, { replace: true });
          } catch (e) {
            console.error("Auto-remix after login failed:", e);
          } finally {
            setIsRemixing(false);
          }
        })();
      }
    } catch {
      // ignore bad JSON
      sessionStorage.removeItem("pendingRemix");
    }
  }, [user, data, slug, nav]);

  const toggleSidebar = () => setIsSidebarVisible((v) => !v);
  const toggleVersionHistory = () => setIsVersionHistoryVisible((v) => !v);

  if (isLoading) {
    return (
      <div className="h-screen flex items-center justify-center">
        <div className="text-center">
          <Loader2 className="w-8 h-8 animate-spin mx-auto mb-4" />
          <p className="text-muted-foreground">Loading shared design...</p>
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="h-screen flex items-center justify-center">
        <div className="text-center max-w-md">
          <h1 className="text-2xl font-bold mb-4">Design Not Found</h1>
          <p className="text-muted-foreground mb-4">
            This shared design link is invalid or has been removed.
          </p>
          <button
            onClick={() => nav("/")}
            className="px-4 py-2 bg-primary text-white rounded hover:bg-primary/90"
          >
            Go to Makistry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-screen overflow-hidden">
      <AuthGateModal
        open={needAuth}
        onClose={() => setNeedAuth(false)}
        onLogin={() => {
          setNeedAuth(false);
          nav(`/login?next=${encodeURIComponent(loc.pathname + loc.search)}`);
        }}
        onSignup={() => {
          setNeedAuth(false);
          nav(`/signup?next=${encodeURIComponent(loc.pathname + loc.search)}`);
        }}
      />

      <ShareTopBar
        projectId={data.project_id}
        projectName={data.title}
        owner={data.owner}
        // prefers username; ShareTopBar should display ownerName if provided
        ownerName={data.owner_username ?? null}
        isSidebarVisible={isSidebarVisible}
        isVersionHistoryVisible={isVersionHistoryVisible}
        onToggleSidebar={toggleSidebar}
        onToggleVersionHistory={toggleVersionHistory}
        isRemixing={isRemixing}
        onRemix={remix}
        // gate sharing if not authed
        isAuthed={!!user}
        onRequireAuth={() => setNeedAuth(true)}
      />

      <div className="flex flex-1 h-[calc(100vh-64px)] overflow-hidden">
        <ChatSection
          initialQuery=""
          projectId={data.project_id}
          isVisible={isSidebarVisible}
          readOnly
          historyBootstrap={chatForBootstrap}
        />

        <ArtifactsSection
          isExpanded={!isSidebarVisible}
          projectId={data.project_id}
          brainstorm={null}
          brainVersion={data.brain_ver}
          cadVersion={data.cad_ver}
          readOnly
        />
      </div>
    </div>
  );
}
