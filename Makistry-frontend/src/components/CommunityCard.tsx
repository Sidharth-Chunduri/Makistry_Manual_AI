import { motion } from "framer-motion";
import { Heart, Repeat } from "lucide-react";
import { CommunityProject } from "@/lib/api/community";
import React, { forwardRef } from "react";
import { UserAvatar } from "@/components/UserAvatar";

interface Props {
  project: CommunityProject;
  onLike: () => void;
  onOpen: () => void;
}

/* Pure visual card – no outer border; Projects-style layout */
export const CommunityCard = forwardRef<HTMLDivElement, Props>(
  ({ project, onLike, onOpen }, ref) => {
    const fallbackSrc =
      project.cadVersion != null
        ? `/api/thumbnail/${project.id}/${project.cadVersion}`
        : `/api/thumbnail/${project.id}/0`;
    return (
        <div
        ref={ref}
        className="group cursor-pointer rounded-2xl bg-card shadow-sm hover:shadow-lg transition overflow-hidden"
        onDoubleClick={onOpen}
        >
        <div className="relative">
            <img
            src={project.preview || fallbackSrc}
            onError={(e) => {
              if (e.currentTarget.src !== window.location.origin + fallbackSrc &&
                  e.currentTarget.src !== fallbackSrc) {
                e.currentTarget.src = fallbackSrc;   // avoid infinite loop
              } else {
                e.currentTarget.src = "/placeholder.png";
              }
            }}
            className="aspect-video w-full object-cover"
            loading="lazy"
            onClick={onOpen}
            />
        {/* like button over the preview */}
        <button
            onClick={(e) => { e.stopPropagation(); onLike(); }}
            className={`
                absolute bottom-2 right-2 z-10 p-1 rounded-full bg-white/80 backdrop-blur transition
                ${project.likedByUser
                ? "opacity-100"                   /* always visible if liked */
                : "opacity-0 group-hover:opacity-100" /* hover-only if not liked */ }
            `}
        >
            {project.likedByUser ? (
                // filled red heart
                <Heart
                stroke="none"
                className="w-6 h-6 fill-red-500 text-red-500"
                />
            ) : (
                // outline only
                <Heart
                fill="none"
                stroke="currentColor"
                className="w-6 h-6 text-red-500"
                />
            )}
        </button>

        {/* optional burst animation */}
        {project.likedByUser && (
            <motion.div
            key="burst"
            className="absolute inset-0 pointer-events-none rounded-2xl bg-red-500/20"
            initial={{ opacity: 0.6 }}
            animate={{ opacity: 0, scale: 1.6 }}
            transition={{ duration: 0.8 }}
            />
        )}
        </div>
        <div role="separator" aria-hidden className="h-px bg-border" />

        {/* footer (maker + stats) */}
        <div className="p-4 flex items-center justify-between">
            <div className="flex items-center gap-2">
            <UserAvatar
            username={project.makerName}
            src={project.makerPhoto}
            size={24}
            className="h-6 w-6"
            tier={project.makerTier ?? "apprentice"} 
            />
            <span className="text-base font-semibold">{project.title}</span>
            </div>
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Heart className="w-4 h-4 stroke-red-500" />
            <span>{project.likesCount}</span>
            <Repeat className="w-4 h-4" />
            <span>{project.remixCount}</span>
            </div>
        </div>
        </div>
    );
  }
);