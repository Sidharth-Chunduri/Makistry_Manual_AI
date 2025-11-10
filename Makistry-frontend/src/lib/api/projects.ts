// src/lib/api/projects.ts
import { api } from "@/lib/api";

export interface ProjectMeta {
  id: string;
  title: string;
  preview?: string | null;
  cadVersion?: number | null;
  updated?: string | null;
  likes: number;
  remix: number;
  private?: boolean;
}

export async function fetchMyProjects(): Promise<ProjectMeta[]> {
  const { data } = await api.get<ProjectMeta[]>("/projects");
  return data;
}

export async function deleteProject(projectId: string): Promise<void> {
  await api.delete(`/projects/${projectId}`);
}

export async function setProjectVisibility(projectId: string, isPrivate: boolean) {
  try {
    const { data } = await api.patch(`/projects/${projectId}/visibility`, {
      private: isPrivate,
    });
    return data as { ok: true; private: boolean };
  } catch (error: any) {
    if (error.response?.status === 402) {
      const e: any = new Error("feature_locked");
      e.code = 402;
      e.detail = error.response.data?.detail ?? error.response.data;
      throw e;
    }
    throw new Error(`Failed to set visibility: ${error.message}`);
  }
}
