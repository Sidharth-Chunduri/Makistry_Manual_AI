// src/lib/api/community.ts
import { api } from "@/lib/api";

export type Tier = "apprentice" | "maker" | "engineer" | "innovator" | "inventor";

export interface CommunityProject {
  id: string;
  title: string;
  preview?: string;
  likesCount: number;
  remixCount: number;
  makerName: string;
  makerPhoto: string | null;
  likedByUser: boolean;
  brainVersion?: number;
  cadVersion?: number;
  makerTier?: Tier;
}

export const fetchCommunity = async (): Promise<CommunityProject[]> => {
  const res = await api.get("/community/feed");
  return res.data;
};

export const toggleLike = async (projectId: string) => {
  const { data } = await api.post("/community/like", { project_id: projectId });
  return data as { liked: boolean; likesCount: number };
};

export const hitView = async (projectId: string) => {
  await api.post("/community/view", { project_id: projectId });
};

export const remixProject = async (srcId: string, stlV: number, brainV: number) => {
  const { data } = await api.post(`/projects/${srcId}/remix`, {
    stl_version: stlV,
    brainstorm_version: brainV,
  });
  return data as { new_project_id: string; name: string };
};
