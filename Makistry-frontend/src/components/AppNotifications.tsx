'use client';

import { useEffect, useMemo, useRef } from "react";
import { useAccount } from "@/hooks/useAccount";
import { useAuth } from "@/hooks/useAuth";
import { listNotifications, markServerNotificationSeen, type Notif } from "@/lib/api/account";
import { toast } from "sonner";
import {
  Bell, Trophy, Crown, Heart, Repeat, MessageSquare, Info, Gauge, Wallet, X,
} from "lucide-react";

function kindIcon(kind?: string) {
  switch (kind) {
    case "badge_level": return <Trophy className="h-5 w-5" aria-hidden="true" />;
    case "tier_up":     return <Crown className="h-5 w-5" aria-hidden="true" />;
    case "like":        return <Heart className="h-5 w-5" aria-hidden="true" />;
    case "remix":       return <Repeat className="h-5 w-5" aria-hidden="true" />;
    case "message":     return <MessageSquare className="h-5 w-5" aria-hidden="true" />;
    case "credit_threshold": return <Gauge className="h-5 w-5" aria-hidden="true" />;
    default:            return <Bell className="h-5 w-5" aria-hidden="true" />;
  }
}

function scopeBadge(n: Notif) {
  const scope = (n.data as any)?.scope as "daily" | "monthly" | "bank" | "stl" | "step" | "projects" | undefined;
  if (!scope) return null;
  const label =
    scope === "daily" ? "Daily" :
    scope === "monthly" ? "Monthly" :
    scope === "bank" ? "Bank" :
    scope === "stl" ? "STL" :
    scope === "step" ? "STEP" : "Projects";

  return (
    <span className="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs text-muted-foreground">
      {scope === "bank" ? <Wallet className="h-3.5 w-3.5" /> : <Gauge className="h-3.5 w-3.5" />}
      {label}
    </span>
  );
}

function usageParts(n: Notif) {
  const d = (n.data as any) || {};
  const used = Number(d.used ?? NaN);
  const total = Number((d.quota ?? d.cap) ?? NaN);
  const pctFromPayload = Number.isFinite(d.percent) ? Number(d.percent) : undefined;
  let pct: number | undefined = pctFromPayload;
  if (pct === undefined && Number.isFinite(used) && Number.isFinite(total) && total > 0) {
    pct = Math.max(0, Math.min(100, Math.round((used / total) * 100)));
  }
  return { pct, used: Number.isFinite(used) ? used : undefined, total: Number.isFinite(total) ? total : undefined };
}

function scopeLabel(scope?: string) {
  return scope === "daily"   ? "Daily"
       : scope === "monthly" ? "Monthly"
       : scope === "bank"    ? "Bank"
       : scope === "stl"     ? "STL"
       : scope === "step"    ? "STEP"
       : scope === "projects"? "Projects"
       : undefined;
}

function friendlyKind(kind?: string) {
  switch (kind) {
    case "credit_threshold": return "Credits";
    case "badge_level": return "Badge";
    case "tier_up": return "Tier";
    default: return kind ? kind.replace(/_/g, " ") : "Info"; 
  }
}

function displayTitle(n: Notif) {
  if (n.kind === "credit_threshold" && (n.data as any)?.scope !== "bank") {
    const scope = scopeLabel((n.data as any)?.scope);
    const { used, total } = usageParts(n);
    if (used !== undefined && total !== undefined) {
      return scope ? `${scope} warning: ${used}/${total} used` : `${used}/${total} used`;
    }
  }
  return n.title || "Notification";
}


function renderToast(n: Notif) {
  return (tId: string) => {
    const isCredit = n.kind === "credit_threshold";
    const scope = (n.data as any)?.scope as string | undefined;
    const { pct, used, total } = usageParts(n);
    const usedLeft = total - used;

    // For credit thresholds (non-bank), suppress percent text in the body.
    const bodyText =
      isCredit && scope !== "bank" && used !== undefined && total !== undefined
        ? `You have ${usedLeft}/${total} left. Upgrade for more.`
        : n.body || "";

    const goUpgrade = () => {
      toast.dismiss(tId);
      window.location.href = "/settings?plan=sub#billing";
    };

    return (
      <div
        role="status"
        aria-live="polite"
        className="w-[360px] bg-white rounded-2xl shadow-lg p-4"
        style={{ 
          border: 'none',
          boxShadow: '0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05)',
          margin: 0,
          padding: '16px'
        }}
      >
        <div className="flex items-start gap-3">
          <div className="mt-0.5 shrink-0">
            {isCredit && scope === "bank" ? (
              <Wallet className="h-5 w-5" aria-hidden="true" />
            ) : (
              kindIcon(n.kind)
            )}
          </div>

          <div className="flex-1 min-w-0">
            {/* title + close */}
            <div className="flex items-start justify-between">
              <div className="flex-1 min-w-0">
                <div className="font-medium text-gray-900">{displayTitle(n)}</div>
              </div>

              <button
                aria-label="Close notification"
                onClick={() => toast.dismiss(tId)}
                className="ml-3 rounded-md p-1.5 hover:bg-gray-100 shrink-0"
              >
                <X className="h-4 w-4" aria-hidden="true" />
              </button>
            </div>

            {/* progress bar */}
            {isCredit && scope !== "bank" && pct !== undefined ? (
              <div className="mt-3">
                <div
                  className="h-1.5 w-full bg-gray-200 rounded-full overflow-hidden"
                  role="meter"
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={pct}
                  aria-label="Usage progress"
                >
                  <div className="h-full bg-[#184777]/70 rounded-full" style={{ width: `${pct}%` }} />
                </div>
              </div>
            ) : null}

            {/* body */}
            {bodyText ? (
              <p className="mt-2 text-sm text-gray-600 break-words">{bodyText}</p>
            ) : null}

            {/* Upgrade button for credit notifications */}
            {isCredit ? (
              <div className="mt-3">
                <button
                  onClick={goUpgrade}
                  className="w-full bg-[#FFCA85] hover:bg-[#FFCA85]/90 text-[#031926] px-3 py-2 rounded-lg text-sm font-medium transition-colors"
                >
                  <Crown className="w-4 h-4 mr-1 inline" />
                  Upgrade
                </button>
              </div>
            ) : null}
          </div>
        </div>
      </div>
    );
  };
}

export default function AppNotifications() {
  const { data: me, error: accountError } = useAccount();
  const { user, token, firebaseReady } = useAuth();

  // Enhanced debug logging
  useEffect(() => {
    console.log("=== AppNotifications State Debug ===");
    console.log("useAuth user:", user);
    console.log("useAuth token:", token ? "EXISTS" : "MISSING");
    console.log("useAuth firebaseReady:", firebaseReady);
    console.log("useAccount me:", me);
    console.log("useAccount error:", accountError);
    console.log("localStorage JWT:", localStorage.getItem("jwt") ? "EXISTS" : "MISSING");
    
    // Decode token for more debug info
    if (token) {
      try {
        const payload = JSON.parse(atob(token.split('.')[1]));
        console.log("Token payload:", payload);
        console.log("Token expires:", new Date(payload.exp * 1000));
        console.log("Token is valid:", new Date() < new Date(payload.exp * 1000));
      } catch (e) {
        console.error("Could not decode token:", e);
      }
    }
  }, [user, token, firebaseReady, me, accountError]);

  // cross-render + cross-tab de-dup
  const seenOnce = useRef<Set<string>>(new Set());
  const isPolling = useRef(false);
  const pollTimer = useRef<NodeJS.Timeout>();
  
  const bc = useMemo(() => {
    try { 
      return new BroadcastChannel("makistry-notifs"); 
    } catch (e) { 
      console.warn("BroadcastChannel not supported:", e);
      return null; 
    }
  }, []);

  useEffect(() => {
    if (!bc) return;
    const onMsg = (e: MessageEvent) => {
      const id = e?.data?.id as string | undefined;
      if (id) {
        console.log("BroadcastChannel received seen notification ID:", id);
        seenOnce.current.add(id);
      }
    };
    bc.onmessage = onMsg;
    return () => { 
      try { 
        bc.close(); 
      } catch (e) {
        console.warn("Error closing BroadcastChannel:", e);
      } 
    };
  }, [bc]);

  // Enhanced poller with multiple fallback conditions
  useEffect(() => {
    // More flexible condition - start polling if we have any user identifier and a valid token
    const hasValidToken = token && localStorage.getItem("jwt");
    const userIdentifier = me?.userID || user?.sub;
    
    console.log("=== Polling Decision ===");
    console.log("hasValidToken:", !!hasValidToken);
    console.log("userIdentifier:", userIdentifier);
    console.log("me?.userID:", me?.userID);
    console.log("user?.sub:", user?.sub);
    
    if (!hasValidToken) {
      console.log("AppNotifications: Not polling - no valid token");
      return;
    }

    if (!userIdentifier) {
      console.log("AppNotifications: Not polling - no user identifier");
      // Don't return early if we have user.sub - useAccount might be slow to load
      if (!user?.sub) {
        return;
      }
      console.log("AppNotifications: Continuing with user.sub as fallback");
    }

    console.log("AppNotifications: Starting notification polling for user:", userIdentifier || user.sub);

    async function tick() {
      if (isPolling.current) {
        console.log("AppNotifications: Already polling, skipping tick");
        return;
      }
      
      isPolling.current = true;
      
      try {
        console.log("=== AppNotifications Debug Poll ===");
        console.log("Current user:", user);
        console.log("Current me:", me);
        console.log("Token exists:", !!token);
        console.log("Local storage JWT:", !!localStorage.getItem("jwt"));
        
        const items = await listNotifications({ onlyUnseen: true, limit: 50 });
        console.log("Raw notifications received:", JSON.stringify(items, null, 2));
        
        if (items.length === 0) {
          console.log("No notifications found - this could mean:");
          console.log("1. No new notifications");
          console.log("2. Authentication issue");
          console.log("3. User identity not found in Firestore");
          console.log("4. Notifications collection doesn't exist");
        }
        
        let newNotifCount = 0;
        for (const n of items) {
          if (seenOnce.current.has(n.id)) {
            console.log("Skipping already seen notification:", n.id);
            continue;
          }
          
          console.log("Showing new notification:", {
            id: n.id,
            kind: n.kind,
            title: n.title,
            body: n.body,
            data: n.data
          });
          
          seenOnce.current.add(n.id);
          
          try {
            bc?.postMessage({ id: n.id });
          } catch (e) {
            console.warn("BroadcastChannel postMessage failed:", e);
          }
          
          toast.custom(renderToast(n), {
            duration: 20_000,
            unstyled: true,                         // keep using your own styles
            className: "bg-transparent shadow-none ring-0 p-0 rounded-none",
            style: { background: "transparent", boxShadow: "none", padding: 0 },
          });
          newNotifCount++;
          
          // mark as seen (best-effort)
          markServerNotificationSeen(n.id).catch((error) => {
            console.warn("Failed to mark notification as seen:", error);
          });
        }
        
        console.log(`Poll completed: ${newNotifCount} new notifications displayed`);
        
      } catch (error) {
        console.error("=== AppNotifications Poll Error ===");
        console.error("Error details:", error);
        
        if (error instanceof Error) {
          console.error("Error message:", error.message);
          
          // Check for common issues
          if (error.message.includes('401')) {
            console.error("→ Authentication failed - token may be expired or invalid");
            console.error("  Current token:", token ? "exists" : "missing");
            console.error("  Local storage:", localStorage.getItem("jwt") ? "exists" : "missing");
          } else if (error.message.includes('404')) {
            console.error("→ Endpoint not found - check if /account/notifications exists");
          } else if (error.message.includes('Failed to fetch')) {
            console.error("→ Network error - backend may be down or unreachable");
          }
        }
      } finally {
        isPolling.current = false;
      }
    }

    // Clear any existing timer
    if (pollTimer.current) {
      clearTimeout(pollTimer.current);
    }

    // Start immediate fetch
    tick();
    
    // Set up recurring polling
    const scheduleNext = () => {
      pollTimer.current = setTimeout(() => {
        tick();
        scheduleNext();
      }, 30000); // 15s cadence
    };
    
    scheduleNext();

    return () => { 
      console.log("AppNotifications: Cleaning up polling");
      if (pollTimer.current) {
        clearTimeout(pollTimer.current);
      }
      isPolling.current = false;
    };
  }, [me?.userID, user?.sub, token, bc]); // Watch token as well

  return null;
}