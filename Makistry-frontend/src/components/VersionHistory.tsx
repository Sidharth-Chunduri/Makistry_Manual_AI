import { ScrollArea } from "@/components/ui/scroll-area";
import { GitBranch } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { fetchVersions } from "@/lib/api/artifacts";

interface VersionHistoryProps {
  isVisible: boolean;
  projectId: string;
  current: number | null;
  onSelect: (b: {
    bundle: number;
    brain_ver: number | null;
    cad_file_ver: number | null;
    cad_code_ver: number | null;
  }) => void;
  disabled?: boolean;
}

export function VersionHistory({
  isVisible,
  projectId,
  current,
  onSelect,
  disabled = false,
}: VersionHistoryProps) {
  const { data: versions = [] } = useQuery({
    queryKey: ["versions", projectId],
    queryFn: () => fetchVersions(projectId),
    enabled: !!projectId,
  });

  if (!isVisible) return null;

  const handleClick = (v: any) => {
    if (disabled) return; // block selection
    onSelect({
      bundle: v.version,
      brain_ver: v.brain_ver ?? null,
      cad_file_ver: v.cad_file_ver ?? null,
      cad_code_ver: v.cad_code_ver ?? null,
    });
  };

  return (
    <div className="w-[35%] bg-background flex flex-col h-full border-r border-border">
      {/* Header */}
      <div className="p-4 border-b border-border flex-shrink-0">
        <h2 className="text-lg font-semibold text-foreground flex items-center gap-2">
          <GitBranch className="w-5 h-5" />
          Version History
        </h2>
        {disabled && (
          <p className="mt-2 text-xs text-muted-foreground">
            Disabled while a process is running...
          </p>
        )}
      </div>

      {/* Version List */}
      <ScrollArea className="flex-1">
        <div className="p-4 space-y-3">
          {versions.map((v: any) => {
            const isCurrent = v.version === current;
            return (
              <div
                key={v.version}
                onClick={() => handleClick(v)}
                aria-disabled={disabled}
                className={`p-3 rounded-lg border cursor-pointer transition-colors ${
                  isCurrent
                    ? "bg-primary/5 border-primary"
                    : "bg-card border-border hover:bg-muted/50"
                }${disabled ? "cursor-not-allowed opacity-60" : "cursor-pointer"}`}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="font-medium">Version {v.version}</span>
                  {isCurrent && (
                    <span className="text-xs bg-primary text-primary-foreground px-2 py-1 rounded">
                      Current
                    </span>
                  )}
                </div>
                <p className="text-sm text-muted-foreground mb-1">
                  {Array.isArray(v.changed) ? v.changed.join(" & ") : v.changed}
                </p>
                <p className="text-xs text-foreground">{v.summary}</p>
              </div>
            );
          })}
        </div>
      </ScrollArea>
    </div>
  );
}
