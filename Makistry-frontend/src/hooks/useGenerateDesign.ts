// src/hooks/useGenerateDesign.ts
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useCreditGate } from "@/stores/useCreditGate";
import { setInFlight, clearInFlight } from "@/lib/inflight";

export interface GenerateResp {
  project_id: string;
  cad_version: number;
  // When using async background STL we DO NOT return blob_url here.
  // Keeping it optional preserves compatibility if you ever switch back.
  blob_url?: string | null;
  code?: string;
  award?: any;
  progressSnapshot?: any;
}

type Vars = { project_id: string };

export const useGenerateDesign = () => {
  const qc = useQueryClient();

  return useMutation<GenerateResp, any, Vars>({
    mutationFn: (body) =>
      api.post<GenerateResp>("/generate-design", body).then((r) => r.data),

    // Sticky flag immediately so UI won't regress if components remount
    onMutate: (vars) => {
      setInFlight("codegen", vars.project_id);
    },

    onSuccess: (data, vars) => {
      // credits/limits may change
      qc.invalidateQueries({ queryKey: ["me"] });

      // IMPORTANT:
      // - If server returned blob_url (sync path), clear sticky now.
      // - If not (async background path), KEEP sticky so ArtifactsSection's
      //   cadPoll keeps polling /latest-cad until STL is ready.
      if (data?.blob_url) {
        clearInFlight("codegen", vars.project_id);
      } else {
        // Safety net: clear after 10 minutes in the absolute worst case so the UI doesn't hang forever.
        // ArtifactsSection will still clear it earlier once it sees a blobUrl via polling.
        setTimeout(() => {
          clearInFlight("codegen", vars.project_id);
        }, 10 * 60 * 1000);
      }
    },

    onError: (err, vars) => {
      const status = err?.response?.status;
      const detail = err?.response?.data;

      // If already running elsewhere, KEEP sticky flag (UI shows spinner) and polling will take over
      if (status === 409 && detail?.error === "in_progress") {
        return;
      }

      // Credit/rate limits → show gate
      if (status === 402 || status === 429) {
        const gate = useCreditGate.getState().openGate;
        gate?.();
      }

      // Other failures → clear so user can retry
      clearInFlight("codegen", vars.project_id);
      // eslint-disable-next-line no-console
      console.error("Generate design failed:", detail ?? err?.message);
    },
  });
};
