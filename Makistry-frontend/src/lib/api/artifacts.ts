// src/lib/api/artifacts.ts
import { api } from "@/lib/api";

// Fetch all version bundles for a project.
export async function fetchVersions(projectId: string) {
  const { data } = await api.get<Array<any>>("/versions", {
    params: { project_id: projectId },
  });
  return data; // → array of {version, changed, summary, ...}
}

// Fetch brainstorm JSON, optionally by version.
export async function fetchBrainstorm(projectId: string, version?: number | null) {
  const { data } = await api.get<{
    status: "ready" | string;
    brainstorm?: unknown;
    version?: number | null;
  }>("/latest-brainstorm", {
    params: {
      project_id: projectId,
      ...(typeof version === "number" ? { version } : {}),
    },
  });

  if (data.status !== "ready") return null;
  return { brainstorm: data.brainstorm, version: data.version ?? null };
}

// Fetch CAD blob URL, optionally by version. Optionally record a view.
export async function fetchCad(
  projectId: string,
  version?: number | null,
  record: boolean = false
) {
  const { data } = await api.get<{
    status: "ready" | string;
    blob_url?: string;
    version?: number;
  }>("/latest-cad", {
    params: {
      project_id: projectId,
      ...(typeof version === "number" ? { version } : {}),
      ...(record ? { record: "true" } : {}),
    },
  });

  if (data.status !== "ready") return null;
  return { blobUrl: data.blob_url as string, version: data.version as number };
}

// Fetch brainstorm PDF bytes (Blob)
export async function fetchBrainstormPDF(projectId: string, version?: number | null) {
  const res = await api.get<Blob>("/export/brainstorm-pdf", {
    params: {
      project_id: projectId,
      ...(typeof version === "number" ? { version } : {}),
    },
    responseType: "blob",
  });
  return res.data; // Blob
}

export type StepResult =
  | { status: "ready"; blobUrl: string; version: number }
  | { status: "pending" };

// Request a STEP export; returns blob URL when ready, null if queued
export async function fetchStep(
  projectId: string,
  cadCodeVersion?: number | null
): Promise<string | null> {
  const { data } = await api.post("/export-step", {
    project_id: projectId,
    cad_code_version: typeof cadCodeVersion === "number" ? cadCodeVersion : null,
  });

  if (data?.pending) return null;                     // 202 "queued" case
  if (typeof data?.blob_url === "string") return data.blob_url; // ready
  throw new Error("Unexpected STEP response");
}

// NEW: poll STEP status (GET) instead of re-POSTing
export async function pollStepStatus(
  projectId: string,
  cadCodeVersion?: number | null,
  opts: { timeoutMs?: number; intervalMs?: number } = {}
): Promise<string> {
  const timeoutMs = opts.timeoutMs ?? 90_000;
  const intervalMs = opts.intervalMs ?? 2000;
  const started = Date.now();

  while (Date.now() - started < timeoutMs) {
    const { data } = await api.get<{ status: "ready" | "pending"; blob_url?: string }>("/step-url", {
      params: {
        project_id: projectId,
        ...(typeof cadCodeVersion === "number" ? { cad_code_version: cadCodeVersion } : {}),
      },
    });
    if (data?.status === "ready" && typeof data.blob_url === "string") {
      return data.blob_url;
    }
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  throw new Error("STEP export timed out");
}
