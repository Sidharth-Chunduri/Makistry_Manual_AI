import React from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger, DropdownMenuSeparator } from "@/components/ui/dropdown-menu";
import { ChevronDown, History, Sidebar, Info, Home, SettingsIcon, ArrowLeftFromLine } from "lucide-react";
import { ShareDropdown } from "@/components/ShareDropdown";

interface ShareTopBarProps {
  projectId: string | null;
  projectName: string | null;
  owner: string | null;
  ownerName?: string | null;
  isSidebarVisible: boolean;
  isVersionHistoryVisible: boolean;
  onToggleSidebar: () => void;
  onToggleVersionHistory: () => void;
  isRemixing: boolean;
  onRemix: () => void;
  isAuthed: boolean;                // NEW
  onRequireAuth: () => void; 
}

export function ShareTopBar({
  projectId,
  projectName,
  owner,
  ownerName,
  isSidebarVisible,
  isVersionHistoryVisible,
  onToggleSidebar,
  onToggleVersionHistory,
  isRemixing,
  onRemix,
  isAuthed, onRequireAuth,
}: ShareTopBarProps) {
  const nav = useNavigate();
  const shareMessage = `Check out "${projectName || "this design"}" I found on Makistry!`;

  return (
    <div className="h-16 bg-background border-b border-border flex items-center justify-between px-6 relative">
      {/* Left: Logo, Project Title, and dropdown like TopBar */}
      <div className="flex items-center gap-4">
        <img src="/Makistry.png" alt="Makistry" className="h-10 w-auto" />
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="sm" className="hover:bg-primary/5">
              <span className="hidden sm:inline text-base">{projectName || "Untitled"}</span>
              <ChevronDown className="w-6 h-6" />
            </Button>
          </DropdownMenuTrigger>

          {/* Workspace menu */}
          <DropdownMenuContent align="start" className="w-80 p-0">
            {/* Top nav item */}
            <div className="px-1 py-1">
              <DropdownMenuItem onSelect={() => nav("/")}>
                <Home className="w-4 h-4 mr-2" />
                Go to dashboard
              </DropdownMenuItem>
            </div>

            <DropdownMenuSeparator />

            {/* Settings / Help buttons (Makistry style) */}
            <div className="mt-3 mb-3 mx-4 grid grid-cols-2 gap-2">
              <Button
                size="sm"
                variant="secondary"
                className="bg-[#031926]/60 hover:bg-[#031926]/90 text-white"
                onClick={() => nav("/settings")}
              >
                <SettingsIcon className="w-4 h-4 mr-1" />
                Settings
              </Button>
              <Button
                asChild
                size="sm"
                variant="secondary"
                className="flex-1 bg-[#031926]/60 hover:bg-[#031926]/90 text-white"
              >
                <a href="https://makistry.com/info" target="_blank" rel="noopener noreferrer">
                  <Info className="w-4 h-4 mr-1" />
                  Help
                </a>
              </Button>
            </div>
            <DropdownMenuSeparator />
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      {/* Middle: Version History & Sidebar toggles */}
      <div
        className="absolute top-4 -translate-x-full flex items-center gap-2 z-10"
        style={{ left: "35%" }}
      >
        <Button
          variant="ghost"
          size="sm"
          onClick={onToggleSidebar}
          className={!isSidebarVisible ? "bg-accent" : ""}
          title={isSidebarVisible ? "Hide Chat" : "Show Chat"}
        >
          <Sidebar className="w-10 h-10" />
        </Button>
      </div>

      {/* Right: Shared by, Share, Remix */}
      <div className="flex items-center gap-4">
        <span className="text-sm text-muted-foreground">
          Shared by {ownerName || "Anonymous"}
        </span>
        {isAuthed ? (
          <ShareDropdown projectId={projectId} url={window.location.href} message={shareMessage} />
        ) : (
          <Button size="sm" variant="outline" onClick={onRequireAuth}>
            Share
          </Button>
        )}
        <Button
          onClick={onRemix}
          disabled={isRemixing}
          size="sm"
          variant="outline"
          className="bg-[#FFCA85] hover:bg-[#FFCA85]/90 text-[#3A2C1C]"
        >
          Remix
        </Button>
      </div>
    </div>
  );
}
