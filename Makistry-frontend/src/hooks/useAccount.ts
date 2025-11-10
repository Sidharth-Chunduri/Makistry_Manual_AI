// src/hooks/useAccount.ts
import { useCallback, useEffect, useMemo } from "react";
import {
  useQuery,
  useQueryClient,
  type UseQueryResult,
} from "@tanstack/react-query";
import { getMe, type AccountMe } from "@/lib/api/account";

export type UseAccountResult = UseQueryResult<AccountMe, Error> & {
  /** Safe: no-ops for guests so we never call /account/me when signed-out. */
  refresh: () => Promise<unknown> | void;
};

export function useAccount(): UseAccountResult {
  const queryClient = useQueryClient();
  const jwt =
    (typeof window !== "undefined" && localStorage.getItem("jwt")) || null;

  const q = useQuery<AccountMe, Error>({
    queryKey: ["me"],
    queryFn: getMe,
    enabled: !!jwt,                 // don’t fetch for guests
    staleTime: 5 * 60 * 1000,       // 5m
    gcTime: 30 * 60 * 1000,         // 30m
    refetchOnWindowFocus: false,
    retry: (failureCount, error) => {
      const msg = String(error?.message ?? "");
      if (msg.includes("401") || /unauthorized/i.test(msg)) return false;
      return failureCount < 1;
    },
  });

  // v5: handle 401 cleanup via an effect
  useEffect(() => {
    if (!q.error) return;
    const msg = String(q.error?.message ?? "");
    if (msg.includes("401") || /unauthorized/i.test(msg)) {
      queryClient.removeQueries({ queryKey: ["me"], exact: true });
    }
  }, [q.error, queryClient]);

  const refresh = useCallback(() => {
    if (!jwt) return;           // guests: do nothing (prevents spinner + 401 spam)
    return q.refetch();
  }, [jwt, q.refetch]);

  // add refresh while preserving the normal query shape
  return useMemo(() => ({ ...q, refresh }), [q, refresh]) as UseAccountResult;
}
