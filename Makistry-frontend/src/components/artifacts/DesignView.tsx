"use client";

import ModelViewer from "@/components/ModelViewer";
import { useRef, useCallback, useState, useEffect } from "react";
import { useAuth } from "@/hooks/useAuth";
import { apiUrl } from "@/lib/api";

interface Props {
  blobUrl: string | null;
  projectId: string;
  cadVersion: number;
}

export default function DesignView({ blobUrl, projectId, cadVersion }: Props) {
  const viewerRef = useRef<{ screenshotBlob: () => Promise<Blob | null> }>(null);
  const { token } = useAuth();
  const [sent, setSent] = useState(false);

  // Always declare hooks first; guard logic inside the hook.
  useEffect(() => {
    setSent(false);
  }, [projectId, cadVersion, blobUrl]);

  // Only attempts upload when everything is ready.
  const handleLoaded = useCallback(async () => {
    if (!blobUrl || !viewerRef.current || sent || !token) return;

    const blob = await viewerRef.current.screenshotBlob();
    if (!blob) return;

    const form = new FormData();
    form.append("project_id", projectId);
    form.append("version", String(cadVersion));
    form.append("file", blob, `${cadVersion}.png`);

    try {
      await fetch(apiUrl("thumbnail"), {
        method: "POST",
        body: form,
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      });
      setSent(true);
    } catch (err) {
      console.error("Thumbnail upload failed:", err);
    }
  }, [blobUrl, projectId, cadVersion, token, sent]);

  // UI branching AFTER all hooks are declared
  if (!blobUrl) {
    return (
      <div className="flex items-center justify-center h-full w-full">
        <div className="text-center">
          <h3 className="text-lg font-semibold mb-2">3D Design Viewer</h3>
          <p className="text-gray-500">
            No design generated yet. Click &quot;Generate Design&quot;
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full w-full flex items-center justify-center overflow-hidden">
      <div className="relative w-full h-full max-w-full max-h-full aspect-square">
        <ModelViewer
          key={`${projectId}:${cadVersion}:${blobUrl}`}
          ref={viewerRef}
          url={blobUrl}
          onLoad={handleLoaded}
          className="absolute inset-0"
        />
      </div>
    </div>
  );
}
