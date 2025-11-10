// src/hooks/useProjects.ts
import { useQuery } from "@tanstack/react-query";
import { fetchMyProjects } from "@/lib/api/projects";

export function useProjects(enabled: boolean, userId?: string | null) {
  return useQuery({
    queryKey: ["my-projects", userId],
    queryFn: fetchMyProjects,
    enabled,
    staleTime: 60_000,
  });
}