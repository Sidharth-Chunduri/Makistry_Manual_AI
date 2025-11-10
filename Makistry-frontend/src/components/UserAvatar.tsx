// userAvatar.tsx
import { useState, useMemo } from "react";
import clsx from "clsx";

type Tier = "apprentice" | "maker" | "engineer" | "innovator" | "inventor";

/** Lighter, more celebratory gradients */
const TIER_BG: Record<Tier, string> = {
  // plain
  apprentice: "bg-gradient-to-br from-slate-50 via-slate-200 to-slate-400",
  // bronze
  maker:      "bg-gradient-to-br from-amber-50 via-amber-200 to-orange-500",
  // silver
  engineer:   "bg-gradient-to-br from-zinc-50 via-zinc-200 to-zinc-400",
  // gold
  innovator:  "bg-gradient-to-br from-yellow-50 via-amber-200 to-yellow-500",
  // diamond
  inventor:   "bg-gradient-to-br from-sky-50 via-cyan-200 to-indigo-300",
};

/** Subtle tier-tinted ring for achievement vibe */
const TIER_RING: Record<Tier, string> = {
  apprentice: "ring-slate-300",
  maker:      "ring-amber-400",
  engineer:   "ring-zinc-300",
  innovator:  "ring-yellow-400",
  inventor:   "ring-cyan-400",
};

interface Props {
  username?: string | null;
  src?: string | null;
  size?: number;
  className?: string;
  alt?: string;
  tier?: Tier;
}

export function UserAvatar({
  username,
  src,
  size = 24,
  className,
  alt,
  tier = "apprentice",
}: Props) {
  const [broken, setBroken] = useState(false);
  const initial = useMemo(() => {
    const u = (username ?? "").replace(/^@/, "").trim();
    return (u[0] || "U").toUpperCase();
  }, [username]);

  if (src && !broken) {
    return (
      <img
        src={src}
        alt={alt || (username ? `${username} avatar` : "User avatar")}
        className={clsx("rounded-full object-cover shrink-0", className)}
        style={{ width: size, height: size }}
        referrerPolicy="no-referrer"
        loading="lazy"
        onError={() => setBroken(true)}
      />
    );
  }

  const isPrestige = tier === "innovator" || tier === "inventor";

  return (
    <span
      className={clsx(
        // base
        "grid place-items-center rounded-full font-semibold uppercase shrink-0 relative overflow-hidden select-none",
        "text-slate-900",
        // depth + soft glow
        "shadow-[inset_0_1px_0_rgba(255,255,255,.65),0_6px_12px_rgba(0,0,0,.12)]",
        "ring-1 ring-offset-[0.5px] ring-offset-white/40 ring-opacity-60",
        TIER_BG[tier],
        TIER_RING[tier],
        className
      )}
      style={{ width: size, height: size, lineHeight: 1 }}
      aria-label={alt || (username ? `${username} avatar` : "User avatar")}
      title={username || undefined}
    >
      <span className="relative z-10 drop-shadow-[0_1px_0_rgba(255,255,255,.6)]">{initial}</span>

      {/* Glossy band (lighter + less gray) */}
      <span className="pointer-events-none absolute inset-0 bg-gradient-to-t from-white/0 via-white/30 to-white/70 opacity-90" />

      {/* Soft radial highlight for “achievement” pop */}
      <span className="pointer-events-none absolute inset-0 opacity-60 mix-blend-soft-light
        bg-[radial-gradient(75%_75%_at_30%_25%,rgba(255,255,255,0.65),transparent_55%)]" />

      {/* Tiny sparkly finish for Gold/Diamond only (tasteful, not flashy) */}
      {isPrestige && (
        <span
          className="pointer-events-none absolute inset-0 opacity-35 mix-blend-overlay
          bg-[radial-gradient(10%_10%_at_70%_25%,rgba(255,255,255,0.8),transparent_60%),radial-gradient(8%_8%_at_35%_75%,rgba(255,255,255,0.55),transparent_65%)]"
        />
      )}
    </span>
  );
}
