// src/components/ShareDropdown.tsx
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import { Copy, Share2, Check } from "lucide-react";
import { buildShareUrls } from "@/lib/share";
import { Switch } from "@/components/ui/switch";
import toast from "react-hot-toast";
import { Button } from "./ui/button";
import { useAccount } from "@/hooks/useAccount";
import { useEffect, useRef, useState } from "react";
import { useActionGate } from "@/stores/useActionGate";
import { setProjectVisibility } from "@/lib/api/projects";
import type { Plan } from "@/lib/api/account";

interface Props {
  url: string;
  message: string;
  projectId: string;
  isPrivate?: boolean;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}

export function ShareDropdown({
  url,
  message,
  projectId,
  isPrivate: initialPrivate = false,
  open,
  onOpenChange,
}: Props) {

  const { data: me } = useAccount();
  const plan: Plan | null = (me?.plan ?? null) as Plan | null;
  const canUsePrivate = plan === "pro";

  const [isPrivate, setIsPrivate] = useState<boolean>(initialPrivate);
  const [saving, setSaving] = useState<boolean>(false);

  const openGate = useActionGate((s) => s.openGate);

  // Sync local state with prop changes
  useEffect(() => {
    setIsPrivate(initialPrivate);
  }, [initialPrivate]);

  // Use crawler-friendly preview URL for social sharing
  const socialTarget =
    url.includes("/share/") ? `${url.replace(/\/$/, "")}/preview`
                            : url.replace("/s/", "/share/") + "/preview";

  const socials = buildShareUrls(socialTarget, message);

  const [copied, setCopied] = useState(false);
  const revertTimer = useRef<number | null>(null);

  const LOGO_META: Record<
    "linkedin" | "reddit" | "facebook" | "twitter",
    { src: string; label: string, scale?: number }
  > = {
    linkedin: { src: "/linkedin.png", label: "LinkedIn", scale: 1.3 },
    reddit:   { src: "/reddit.png", label: "Reddit", scale: 1.3   },
    facebook: { src: "/fa.png", label: "Facebook", scale: 1.3 },
    twitter:  { src: "/X.webp", label: "X (Twitter)", scale: 2 },
  };

  // Row order: [LinkedIn, Reddit], [Facebook, X]
  const GRID_ORDER: Array<Array<keyof typeof LOGO_META>> = [
    ["linkedin", "reddit"],
    ["facebook", "twitter"],
  ];

  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(url);
    } catch {
      const textArea = document.createElement("textarea");
      textArea.value = url;
      document.body.appendChild(textArea);
      textArea.select();
      document.execCommand("copy");
      document.body.removeChild(textArea);
    }
    setCopied(true);
    if (revertTimer.current) window.clearTimeout(revertTimer.current);
    revertTimer.current = window.setTimeout(() => setCopied(false), 1500);
  };

  const onTogglePrivate = async (next: boolean) => {
    if (!me) {
      toast.error("Please sign in to change visibility");
      return;
    }
    
    if (next && !canUsePrivate) {
      openGate({ plan: (plan ?? "free") as Plan, action: "private_projects" });
      return;
    }
    
    const prev = isPrivate;
    setIsPrivate(next);
    setSaving(true);

    try {
      const res = await setProjectVisibility(projectId, next);
      setIsPrivate(res.private); // confirm from server
      toast.success(`Project is now ${res.private ? 'private' : 'public'}`);
    } catch (e: any) {
      setIsPrivate(prev);        // revert on error
      console.error('Error updating visibility:', e);
      
      if (e?.code === 402 || e?.detail?.feature === "private_projects") {
        openGate({ plan: (plan ?? "free") as Plan, action: "private_projects" });
      } else {
        toast.error("Couldn't update visibility. Please try again.");
      }
    } finally {
      setSaving(false);
    }
  };

  const openSocial = (socialUrl: string) => {
    const width = 600;
    const height = 400;
    const left = (window.innerWidth - width) / 2;
    const top = (window.innerHeight - height) / 2;

    window.open(
      socialUrl,
      "_blank",
      `width=${width},height=${height},left=${left},top=${top},resizable=yes,scrollbars=yes`
    );

    // Close the menu after clicking a logo (if controlled)
    onOpenChange?.(false);
  };

  useEffect(() => {
    return () => { if (revertTimer.current) window.clearTimeout(revertTimer.current!); };
  }, []);

  return (
    <DropdownMenu open={open} onOpenChange={onOpenChange}>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" className="hover:bg-[#031926]/10">
          <Share2 className="w-4 h-4 mr-1" />
          Share
        </Button>
      </DropdownMenuTrigger>

      {/* Wider to fit 2x2 logo grid nicely */}
      <DropdownMenuContent align="end" className="w-56">
        {/* Visibility toggle row */}
        <div className="px-3 py-2">
          <div className="flex items-center justify-between w-full">
            <div className="text-sm">
              <div className="font-medium text-foreground">{isPrivate ? "Private" : "Public"}</div>
              <div className="text-xs text-muted-foreground">
                {isPrivate ? "Hidden from Community" : "Visible in Community"}
              </div>
            </div>

            <Switch
              checked={isPrivate}
              onCheckedChange={onTogglePrivate}
              disabled={saving || !me}
              aria-label="Toggle private project"
            />
          </div>
        </div>

        <DropdownMenuSeparator />

        {/* 2x2 grid of brand logo buttons */}
        <div className="grid grid-cols-2 gap-2 p-2">
          {GRID_ORDER.flat().map((key) => {
            const meta = LOGO_META[key];
            const url = socials[key];

            return (
              <button
                key={key}
                type="button"
                onClick={() => openSocial(url)}
                title={meta.label}
                aria-label={meta.label}
                className="flex items-center justify-center rounded-lg border border-border p-3
                           hover:bg-muted transition-colors"
              >
                <img
                  src={meta.src}
                  alt={meta.label}
                  className="h-6 w-6"
                  style={{ transform: `scale(${meta.scale ?? 1})` }}
                  loading="lazy"
                  draggable={false}
                />
                <span className="sr-only">{meta.label}</span>
              </button>
            );
          })}
        </div>

        <DropdownMenuSeparator />

        {/* Copy link at the very bottom */}
        <DropdownMenuItem
          onSelect={(e) => { e.preventDefault(); copyLink(); }} // keep dropdown open
          className="cursor-pointer"
        >
          {copied ? (
            <>
              <Check className="w-4 h-4 mr-2" />
              Copied!
            </>
          ) : (
            <>
              <Copy className="w-4 h-4 mr-2" />
              Copy link
            </>
          )}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}