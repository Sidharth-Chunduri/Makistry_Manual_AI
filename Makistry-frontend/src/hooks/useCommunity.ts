// hooks/useCommunity.ts
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchCommunity, toggleLike } from "@/lib/api/community";
import type { CommunityProject } from "@/lib/api/community";
import { useAuth } from "@/hooks/useAuth";

export function useCommunity() {
  const qc = useQueryClient();
  const { user } = useAuth();

  /* ---------- FEED (fetch once, then keep) ---------- */
  const feed = useQuery<CommunityProject[]>({
    queryKey: ["community"],
    queryFn: fetchCommunity,
    // BootstrapLoader should already set this cache; this ensures no refetch on mount
    refetchOnMount: false,
    refetchOnWindowFocus: false,
    staleTime: 10 * 60_000,  // 10 minutes
    gcTime: 30 * 60_000,
  });

  /* ---------- LIKE (optimistic + reconcile; no refetch) ---------- */
  type LikeResponse = { liked: boolean; likesCount: number };

  const likeMut = useMutation<LikeResponse, Error, string, { prev?: CommunityProject[] }>({
    mutationFn: (pid) => toggleLike(pid) as unknown as Promise<LikeResponse>,

    onMutate: async (pid) => {
      await qc.cancelQueries({ queryKey: ["community"] });

      const prev = qc.getQueryData<CommunityProject[]>(["community"]);
      // optimistic flip
      qc.setQueryData<CommunityProject[]>(["community"], (old) =>
        (old ?? []).map((p) =>
          p.id === pid
            ? {
                ...p,
                likesCount: p.likedByUser ? p.likesCount - 1 : p.likesCount + 1,
                likedByUser: !p.likedByUser,
              }
            : p
        )
      );
      return { prev };
    },

    onError: (_err, _pid, ctx) => {
      // rollback if the server call failed
      qc.setQueryData(["community"], ctx?.prev);
    },

    onSuccess: (res, pid) => {
      // commit the server’s authoritative values for ONLY that card
      qc.setQueryData<CommunityProject[]>(["community"], (old) =>
        (old ?? []).map((p) =>
          p.id === pid
            ? { ...p, likedByUser: res.liked, likesCount: res.likesCount }
            : p
        )
      );
    },

    // DO NOT invalidate; we already reconciled locally
    onSettled: () => {},
  });

  return { feed, likeMut };
}
