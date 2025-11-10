"use client";

import { useState } from "react";
import { useGenerateDesign } from "@/hooks/useGenerateDesign";
import ModelViewer from "@/components/ModelViewer";
import { toast } from "sonner";
import { useProgressStore } from "@/stores/useProgressStore";
import { recordProgress } from "@/lib/api/account";
import { toastFromCategoryAward } from "@/lib/progressToasts";
import type { ProgressSnapshot } from "@/lib/api/account";

export default function ActionButtons({ projectId }: { projectId: string }) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const gen = useGenerateDesign();
  const { snapshot, setSnapshot } = useProgressStore();

  type GenerateResp = {
    blob_url?: string | null;
    progress?: ProgressSnapshot; // present if you added it server-side
  };

  const handleGenerate = async () => {
    try {
      const data = (await gen.mutateAsync({ project_id: projectId })) as unknown as GenerateResp;
      setBlobUrl(data?.blob_url ?? null);

      // Record progress for creating a design
      try {
        const { award, snapshot: newSnapshot } = await recordProgress({
          category: "designs",
          uniqueKey: projectId // Only award once per project
        });
        
        // Show toast and update store
        toastFromCategoryAward("designs", award, snapshot, newSnapshot);
        setSnapshot(newSnapshot);
      } catch (progressError) {
        // Don't fail the whole operation if progress fails
        console.warn("Progress recording failed:", progressError);
        // Still show success for the main operation
        toast.success("Design generated!");
      }

      // If we didn't show a progress toast, show the regular success
      if (!snapshot) {
        toast.success("Design generated!");
      }
      
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Generation error");
    }
  };

  return (
    <div className="space-y-8">
      {/* buttons */}
      <div className="flex flex-wrap gap-4">
        <button
          className="rounded bg-emerald-600 px-4 py-2 text-white disabled:opacity-50"
          onClick={handleGenerate}
          disabled={gen.isPending}
        >
          {gen.isPending ? "Generating…" : "Generate Design"}
        </button>
      </div>

      {/* 3-D view */}
      {blobUrl && (
        <div>
          <h3 className="mb-2 text-lg font-medium">3-D Preview</h3>
          <ModelViewer url={blobUrl} className="h-full w-full" />
        </div>
      )}
    </div>
  );
}