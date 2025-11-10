import { useMutation } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useQueryClient } from "@tanstack/react-query";
import { useCreditGate } from "@/stores/useCreditGate";
import { useActionGate } from "@/stores/useActionGate";
import type { ActionLimits } from "@/stores/useActionGate";
import { useAccount } from "@/hooks/useAccount";


/** ---------------- Types returned by /brainstorm ---------------- */
export interface BrainstormJSON {
  design_one_liner: string;
  project_name:      string;
  key_features:      string[];
  key_functionalities: string[];
  design_components: string[];
  optimal_geometry:  Record<string, string | number>;
  /** any extra fields … */
  [k: string]: unknown;
}

export interface BrainstormResp {
  project_id: string;
  brainstorm: BrainstormJSON;
}

export const useBrainstorm = () => {
  const { data: me } = useAccount();
  const openActionGate = useActionGate((s) => s.openGate);
  const qc = useQueryClient();
  const openGate = useCreditGate((s) => s.openGate);
  return useMutation<BrainstormResp, Error, string>({
    mutationFn: (prompt) =>
      api.post("/brainstorm", { prompt }).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["me"] });
    },
    onError: (err: any) => {
      const status = err?.response?.status;
      if (status !== 402) return;

      const detail = err?.response?.data?.detail ?? err?.response?.data ?? null;
      const plan = (me?.plan as any) ?? "free";

      if (detail?.error === "limit_reached_action" && detail?.action === "project_create") {
        openActionGate({
          plan,
          action: "project_create",
          limits: detail.limits as ActionLimits,
          gateFor: "brainstorm",
        });
        return;
      }

      if (detail?.error === "credit_limit_reached") {
        // Open existing CreditGate
        openGate();
      }
    },
  });
};
