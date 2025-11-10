import { useEffect, useRef } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "@/hooks/useAuth";
import { readPending, clearPending } from "@/lib/pendingActions";
import { remixProject } from "@/lib/api/community";

// NEW imports
import { api } from "@/lib/api";
// If you already have helpers, use them instead:
// import { toggleLike } from "@/lib/api/community";

export default function PendingActionRunner() {
  const { user } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const runningRef = useRef(false);

  useEffect(() => {
    if (!user || runningRef.current) return;
    const pending = readPending();
    if (!pending) return;

    runningRef.current = true;

    (async () => {
      try {
        // Navigate back to where the action was queued (helps SPA context)
        if (pending.next && (loc.pathname + loc.search) !== pending.next) {
          nav(pending.next, { replace: true });
          await new Promise((r) => setTimeout(r, 0));
        }

        const { action } = pending;

        switch (action.type) {
          case "remix": {
            const res = await remixProject(
              action.payload.srcProjectId,
              action.payload.cadVersion,
              action.payload.brainVersion
            );
            clearPending();
            nav(`/project/${res.new_project_id}`, { replace: true });
            break;
          }

          case "brainstorm": {
            // Call your backend brainstorm API
            const { data } = await api.post("/brainstorm", {
              prompt: action.payload.prompt,
            });
            // Expecting { project_id, brainstorm }
            clearPending();
            nav(`/project/${data.project_id}`, { replace: true });
            break;
          }

          case "like": {
            // If you have a proper API helper use it here
            await api.post(`/community/${action.payload.projectId}/like`);
            // You might want to trigger a cache refetch via react-query (optional)
            clearPending();
            // Stay on same page; router state/UI will re-render once authed
            break;
          }

          default:
            clearPending();
        }
      } catch (err) {
        console.error("Pending action failed:", err);
        clearPending();
        nav("/", { replace: true });
      } finally {
        runningRef.current = false;
      }
    })();
  }, [user, nav, loc]);

  return null;
}
