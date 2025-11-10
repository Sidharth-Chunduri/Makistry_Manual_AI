// src/components/GlobalLoadingCursor.tsx
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useIsFetching, useIsMutating } from "@tanstack/react-query";
import { BusyCursor } from "@/lib/busyCursor";

type Props = {
  /** Delay before showing busy UI (ms) to avoid flicker */
  delayMs?: number;
  /** Path to your logo asset; SVG preferred for crisp scaling */
  logoSrc?: string;
  /** Size of the logo cursor in CSS px */
  size?: number;
  /** Use logo overlay when possible; falls back to system spinner otherwise */
  useLogo?: boolean;
};

export function GlobalLoadingCursor({
  delayMs = 200,
  logoSrc = "/just_M.png", // <-- set this to your logo path
  size = 35,
  useLogo = true,
}: Props) {
  const fetchCount = useIsFetching();
  const mutateCount = useIsMutating();

  // Track manual busy count
  const [manualCount, setManualCount] = useState(BusyCursor.count);
  useEffect(() => BusyCursor.subscribe(() => setManualCount(BusyCursor.count)), []);

  const active = (fetchCount + mutateCount + manualCount) > 0;

  // Pointer type & debounce
  const [show, setShow] = useState(false);
  const timerRef = useRef<number | null>(null);
  const supportsFinePointer =
    typeof window !== "undefined"
      ? window.matchMedia?.("(pointer: fine)")?.matches ?? true
      : true;

  useEffect(() => {
    const root = document.documentElement;
    const clearTimer = () => {
      if (timerRef.current) {
        window.clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };

    if (active) {
      clearTimer();
      if (!show) {
        timerRef.current = window.setTimeout(() => setShow(true), delayMs);
      }
    } else {
      clearTimer();
      setShow(false);
    }

    // Toggle html classes depending on mode & capability
    const useLogoNow = useLogo && supportsFinePointer;
    if (show && active && useLogoNow) {
      root.classList.add("cursor-logo");
      root.classList.remove("cursor-progress");
    } else if (show && active) {
      root.classList.add("cursor-progress");
      root.classList.remove("cursor-logo");
    } else {
      root.classList.remove("cursor-logo");
      root.classList.remove("cursor-progress");
    }

    return () => {
      clearTimer();
    };
  }, [active, delayMs, useLogo, supportsFinePointer, show]);

  // Track pointer position only while visible
  const [pos, setPos] = useState<{ x: number; y: number }>({ x: -9999, y: -9999 });
  useEffect(() => {
    if (!(show && active && useLogo && supportsFinePointer)) return;

    let raf = 0;
    let lastX = pos.x;
    let lastY = pos.y;

    const onMove = (e: MouseEvent) => {
      lastX = e.clientX;
      lastY = e.clientY;
      if (!raf) {
        raf = requestAnimationFrame(() => {
          raf = 0;
          setPos({ x: lastX, y: lastY });
        });
      }
    };

    window.addEventListener("mousemove", onMove, { passive: true });
    return () => {
      window.removeEventListener("mousemove", onMove);
      if (raf) cancelAnimationFrame(raf);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [show, active, useLogo, supportsFinePointer]);

  const shouldRenderLogo = show && active && useLogo && supportsFinePointer;

  return (
    <>
      {shouldRenderLogo &&
        createPortal(
          <div
            className="mk-cursor"
            style={{ left: pos.x, top: pos.y, width: size, height: size }}
            aria-hidden
          >
            {/* Option A: SVG logo (best). If your SVG uses stroke/fill="currentColor" it will theme automatically */}
            {logoSrc.endsWith(".svg") ? (
              // If your logo SVG is simple, you can inline it; otherwise <img> is fine.
              <img src={logoSrc} className="mk-cursor__icon" alt="" />
            ) : (
              // Option B: Raster (PNG/WebP) also works
              <img src={logoSrc} className="mk-cursor__icon" alt="" />
            )}
          </div>,
          document.body
        )}
    </>
  );
}
