import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Card, CardContent } from "@/components/ui/card";
import ModelViewer from "@/components/ModelViewer";
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useCommunity } from "@/hooks/useCommunity";
import { hitView, remixProject } from "@/lib/api/community";
import { Button } from "@/components/ui/button";
import { CommunityCard } from "./CommunityCard";
import { CommunityProject } from "@/lib/api/community";
import { useAuth } from "@/hooks/useAuth";
import { fetchCad } from "@/lib/api/artifacts";
import { useNavigate } from "react-router-dom";
import { AuthGateModal } from "@/components/AuthGateModal";
import { UserAvatar } from "@/components/UserAvatar";
import { queueAuthAction } from "@/lib/pendingActions";
import { VisuallyHidden } from "@radix-ui/react-visually-hidden";

export function CommunitySection() {
  const { feed, likeMut } = useCommunity();
  const { user } = useAuth();
  const nav = useNavigate();

  // Local UI state
  const [openId, setOpenId] = useState<string | null>(null);
  const [stlUrl, setStlUrl] = useState<string | null>(null);
  const [ordered, setOrdered] = useState<CommunityProject[] | null>(null);
  const [needAuth, setNeedAuth] = useState(false);

  const nextPath =
    typeof window !== "undefined"
      ? window.location.pathname + window.location.search
      : "/";

  const sortByPopularity = useCallback(
    (list: CommunityProject[]) =>
      list
        .filter((p) => p.cadVersion != null)
        .slice()
        .sort(
          (a, b) =>
            (b.likesCount ?? 0) - (a.likesCount ?? 0) ||
            (b.remixCount ?? 0) - (a.remixCount ?? 0) ||
            a.title.localeCompare(b.title)
        ),
    []
  );

  // Keep a stable order but merge fresh fields when the set of items is the same
  useEffect(() => {
    if (!feed.data) return;
    setOrdered((prev) => {
      if (!prev) return sortByPopularity(feed.data);

      const prevIds = new Set(prev.map((p) => p.id));
      const newIds = new Set(feed.data.map((p) => p.id));
      const sameSet =
        prevIds.size === newIds.size &&
        [...prevIds].every((id) => newIds.has(id));

      if (!sameSet) {
        return sortByPopularity(feed.data);
      }
      const byId = new Map(feed.data.map((p) => [p.id, p]));
      return prev.map((p) => ({ ...p, ...(byId.get(p.id) ?? p) }));
    });
  }, [feed.data, sortByPopularity]);

  // Derive selected from openId + latest feed snapshot (no separate state)
  const selected = useMemo(() => {
    if (!openId) return null;
    const pool = ordered ?? feed.data ?? [];
    const sel = pool.find((p) => p.id === openId) ?? null;
    if (!sel) console.debug("[CommunitySection] openId set, but project not found in feed", { openId, poolSize: pool.length });
    return sel;
  }, [openId, ordered, feed.data]);

  // Fetch STL whenever the selected card changes
  useEffect(() => {
    let cancelled = false;
    setStlUrl(null);

    (async () => {
      if (!selected?.cadVersion) return;
      try {
        const cad = await fetchCad(selected.id, selected.cadVersion);

        // Handle both backend/raw shapes and any client-normalized shapes.
        const url =
          cad?.blobUrl ?? null;
        if (!url) console.warn("[CommunitySection] No STL URL in response", cad);

        console.debug("[CommunitySection] fetchCad ->", cad, "resolvedUrl:", url);

        if (!cancelled) setStlUrl(url);
      } catch (e) {
        console.error("[CommunitySection] fetchCad failed", e);
        if (!cancelled) setStlUrl(null);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [selected?.id, selected?.cadVersion]);


  const visibleFeed = useMemo(
    () => (ordered ?? feed.data ?? []).filter((p) => p.cadVersion != null),
    [ordered, feed.data]
  );

  // Handlers
  const openModal = (p: CommunityProject) => {
    console.debug("[CommunitySection] opening modal for", p.id, "cadVersion:", p.cadVersion);
    setOpenId(p.id);
    hitView(p.id);
  };

  const handleRemix = async () => {
    if (!selected) return;

    if (!user) {
      queueAuthAction(
        {
          type: "remix",
          payload: {
            srcProjectId: selected.id,
            cadVersion: selected.cadVersion!,
            brainVersion: selected.brainVersion ?? 1,
          },
        },
        nextPath
      );
      setOpenId(null);
      setNeedAuth(true);
      return;
    }

    try {
      const res = await remixProject(
        selected.id,
        selected.cadVersion!,
        selected.brainVersion ?? 1
      );
      nav(`/project/${res.new_project_id}`);
    } catch (e) {
      console.error("Remix failed", e);
    }
  };

  const isLoading = feed.isLoading || !feed.data;

  return (
    <section id="community" className="bg-background py-14 scroll-mt-24">
      <AuthGateModal
        open={needAuth}
        onClose={() => setNeedAuth(false)}
        onLogin={() => {
          setNeedAuth(false);
          nav(`/login?next=${encodeURIComponent(nextPath)}`);
        }}
        onSignup={() => {
          setNeedAuth(false);
          nav(`/signup?next=${encodeURIComponent(nextPath)}`);
        }}
      />

      <div className="mx-auto max-w-7xl px-4 sm:px-6">
        <h2 className="text-2xl font-bold text-foreground">Community Makerspace</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          Explore what other Makers are making. Preview, like, and remix designs!
        </p>

        {isLoading ? (
          <div className="mt-8 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {/* simple skeletons */}
            {[...Array(6)].map((_, i) => (
              <div key={i} className="h-48 rounded-2xl bg-muted animate-pulse" />
            ))}
          </div>
        ) : (
          <div className="mt-8 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {visibleFeed.map((p) => (
              <Card key={p.id} className="hover:shadow transition">
                <CardContent className="p-0">
                  <CommunityCard
                    project={p}
                    onLike={() => {
                      if (!user) {
                        queueAuthAction(
                          { type: "like", payload: { projectId: p.id } },
                          nextPath
                        );
                        setNeedAuth(true);
                        return;
                      }
                      likeMut.mutate(p.id);
                    }}
                    onOpen={() => openModal(p)}
                  />
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>

      {/* One dialog outside the map */}
      <Dialog
        open={openId !== null}
        onOpenChange={(v) => {
          if (!v) {
            setOpenId(null);
            setStlUrl(null);
          }
        }}
      >
        <DialogContent
          aria-describedby={undefined}
          className="fixed z-[60] max-w-6xl w-[90vw] h-[85vh] p-0 flex flex-col overflow-hidden [&>button]:hidden"
        >
          <VisuallyHidden asChild>
            <DialogTitle>{selected?.title || "Project preview"}</DialogTitle>
          </VisuallyHidden>
          <VisuallyHidden asChild>
            <DialogDescription>
              Interact with a 3D preview of this project. Press Escape to close.
            </DialogDescription>
          </VisuallyHidden>

          <div className="flex items-center justify-between p-4">
            <div className="flex items-center gap-3">
              <UserAvatar
                username={selected?.makerName}
                src={selected?.makerPhoto}
                size={32}
                className="h-8 w-8"
              />
              <div className="flex flex-col leading-tight">
                <h3 className="text-lg font-semibold">
                  {selected?.title || "Loading…"}
                </h3>
                <span className="text-sm text-muted-foreground">
                  {selected ? `by ${selected.makerName ?? "maker"}` : ""}
                </span>
              </div>
            </div>
            <Button
              size="lg"
              className="h-11 px-6 text-base rounded-lg shadow-sm"
              onClick={handleRemix}
              aria-label="Remix this project"
              disabled={!selected}
            >
              Remix
            </Button>
          </div>

          <div className="flex-1 min-h-0">
            {stlUrl ? (
              <ModelViewer url={stlUrl} className="h-full" autoRotate />
            ) : (
              <div className="h-full flex items-center justify-center text-sm text-muted-foreground">
                Loading model…
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </section>
  );
}
