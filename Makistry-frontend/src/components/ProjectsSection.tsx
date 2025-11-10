import { formatDistanceToNow } from "date-fns";
import { Ellipsis, Heart, Repeat } from "lucide-react";
import { DropdownMenu, DropdownMenuTrigger,
         DropdownMenuContent, DropdownMenuItem } from "@/components/ui/dropdown-menu";
import { Card, CardContent } from "@/components/ui/card";
import { type ProjectMeta } from "@/lib/api/projects";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api"; 
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, useEffect } from "react";
import { deleteProject } from "@/lib/api/projects";

interface Props {
  projects: ProjectMeta[];
}

export function ProjectsSection({ projects }: Props) {
  const nav = useNavigate();
  const qc  = useQueryClient();
  const [localProjects, setLocalProjects] = useState<ProjectMeta[]>(projects);
  const [editId, setEditId]         = useState<string | null>(null);
  const [draftTitle, setDraftTitle] = useState<string>("");
  const [deleteId, setDeleteId]     = useState<string | null>(null);

  // Keep localProjects in sync when the prop changes
  useEffect(() => {
    setLocalProjects(projects);
  }, [projects]);

  const delMut = useMutation<void, Error, string>({
    mutationFn: deleteProject,
    onSuccess: (_, pid) => {
      // Evict from local & react-query cache
      qc.setQueryData<ProjectMeta[]>(["my-projects"], (old) =>
        (old ?? []).filter((p) => p.id !== pid),
      );
      setLocalProjects((cur) => cur.filter((p) => p.id !== pid));
      setDeleteId(null);
      // Community feed will drop it on next refetch automatically
      qc.invalidateQueries({ queryKey: ["community"] });
    },
  });

  // --- Refresh logic: one-shot on arrival + on tab focus (no polling) ---
  useEffect(() => {
    let cleanup = () => {};

    // 1) If we navigated here via “Go to dashboard”, refetch once.
    if (sessionStorage.getItem("projects:refreshOnNextDashboard") === "1") {
      sessionStorage.removeItem("projects:refreshOnNextDashboard");
      qc.invalidateQueries({ queryKey: ["my-projects"] });
    }

    // Helper to compare server "tick" and refetch only if changed.
    const maybeRefetchOnFocus = async () => {
      try {
        const { data } = await api.get<{ latest: number }>("/projects/tick");
        const latest = Number(data?.latest ?? 0);
        const prev   = Number(sessionStorage.getItem("projects:latest") || 0);
        if (latest > prev) {
          qc.invalidateQueries({ queryKey: ["my-projects"] });
          sessionStorage.setItem("projects:latest", String(latest));
        }
      } catch {
        // Best-effort; ignore tick errors.
      }
    };

    // 2) Seed the stored tick on first mount so the comparison works.
    maybeRefetchOnFocus();

    // 3) When user returns focus to the dashboard tab, check & maybe refetch.
    const onVis = () => {
      if (document.visibilityState === "visible") {
        void maybeRefetchOnFocus();
      }
    };
    document.addEventListener("visibilitychange", onVis);
    cleanup = () => document.removeEventListener("visibilitychange", onVis);

    return cleanup;
  }, [qc]);

  // show a friendly empty state if they have no projects yet
  if (projects.length === 0) {
    return (
      <section id="projects" className="bg-background scroll-mt-24 -mt-10">
        <div className="mx-auto w-full max-w-7xl px-4 sm:px-6">
          <div className="pt-8 sm:pt-10">
            <h2 className="text-2xl font-bold text-foreground">Projects</h2>
            <p className="mt-2 text-sm text-muted-foreground">
              You haven’t created any projects yet.
            </p>
          </div>
          <div className="mt-8 text-center text-sm text-muted-foreground">
            Start by typing a prompt above and click “Think” to spin up your first project.
          </div>
          <div className="h-16" />
        </div>
      </section>
    );
  }

  return (
    <section id="projects" className="bg-background scroll-mt-24 -mt-10">
      <div className="mx-auto w-full max-w-7xl px-4 sm:px-6">
        <div className="pt-8 sm:pt-10">
          <h2 className="text-2xl font-bold text-foreground">Projects</h2>
          <p className="mt-2 text-sm text-muted-foreground">
            View your projects and resume where you left off!
          </p>
        </div>

        <div className="mt-8 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {localProjects.map((p) => (
            <Card key={p.id} className="hover:shadow transition">
              <div
                className={`aspect-video w-full rounded-t-2xl cursor-pointer flex items-center justify-center ${
                  p.preview
                    ? "bg-white bg-cover bg-center"
                    : "bg-white text-xs text-muted-foreground"
                }`}
                style={p.preview ? { backgroundImage: `url("${p.preview}")` } : undefined}
                onClick={() => nav(`/project/${p.id}`)}
              >
                {!p.preview && !p.cadVersion && (
                  <span className="px-6 text-center">
                    Generate design to see preview
                  </span>
                )}
              </div>
              <div role="separator" aria-hidden className="h-px bg-border" />
              <CardContent className="p-4 flex justify-between items-start">
                <div className="flex-1 min-w-0">
                  {editId === p.id ? (
                    <input
                      autoFocus
                      className="border rounded px-2 py-1 text-sm w-full"
                      value={draftTitle}
                      onChange={(e) => setDraftTitle(e.target.value)}
                      onBlur={async () => {
                        setEditId(null);
                        const newTitle = draftTitle.trim();
                        if (newTitle && newTitle !== p.title) {
                          // Optimistic UI update
                          setLocalProjects(cur =>
                            cur.map(x => x.id === p.id ? { ...x, title: newTitle } : x)
                          );
                          try {
                            // Persist to backend
                            await api.patch(`/projects/${p.id}/title`, { title: newTitle });
                            // Update react-query cache
                            qc.setQueryData<ProjectMeta[]>(
                              ["my-projects"],
                              old => (old ?? []).map(x =>
                                x.id === p.id ? { ...x, title: newTitle } : x
                              )
                            );
                          } catch {
                            // rollback on error
                            setLocalProjects(cur =>
                              cur.map(x => x.id === p.id ? { ...x, title: p.title } : x)
                            );
                          }
                        }
                      }}
                    />
                  ) : (
                    <h3 className="text-base font-semibold text-foreground">
                      {p.title}
                    </h3>
                  )}
                  {p.updated && (
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      opened {formatDistanceToNow(new Date(p.updated))} ago
                    </p>
                  )}
                </div>
                <div className="flex flex-col items-end gap-1">
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <button className="p-1 rounded-full hover:bg-primary/10">
                        <Ellipsis className="w-5 h-5 text-foreground/80" />
                      </button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuItem onSelect={() => nav(`/project/${p.id}`)}>
                        Continue
                      </DropdownMenuItem>
                      <DropdownMenuItem
                        onSelect={() => {
                          setEditId(p.id);
                          setDraftTitle(p.title);
                        }}
                      >
                        Rename
                      </DropdownMenuItem>
                      <DropdownMenuItem
                        className="text-destructive"
                        onSelect={() => setDeleteId(p.id)}
                      >
                        Delete
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                  {/* likes & remix counters */}
                  <div className="flex items-center gap-4 text-xs text-muted-foreground">
                    <div className="flex items-center gap-1">
                      <Heart  className="w-4 h-4 stroke-red-500" />
                      {p.likes > 0 && <span>{p.likes}</span>}
                    </div>
                    <div className="flex items-center gap-1">
                      <Repeat className="w-4 h-4" />
                      {p.remix > 0 && <span>{p.remix}</span>}
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
        {/* Delete confirmation overlay */}
        {deleteId && (
          <div className="fixed inset-0 flex items-center justify-center bg-black/40">
            <div className="bg-background p-6 rounded-lg shadow-lg max-w-sm">
              <h2 className="text-lg font-semibold">Are you sure you want to delete this project?</h2>
              <p className="mt-2 text-sm text-muted-foreground">
                This deletes all information related to this project and you won't be able to restore it.
              </p>
              <div className="mt-4 flex justify-end gap-3">
                <button
                  className="px-4 py-2 border rounded"
                  onClick={() => setDeleteId(null)}
                >
                  Cancel
                </button>
                <button
                  className="px-4 py-2 bg-red-600 text-white rounded"
                  onClick={() => deleteId && delMut.mutate(deleteId)}
                >
                  Delete
                </button>
              </div>
            </div>
          </div>
        )}

        <div className="h-16" />
      </div>
    </section>
  );
}