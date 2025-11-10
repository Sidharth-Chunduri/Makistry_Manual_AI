import { useEffect, useRef, useState, useMemo } from "react";
import { ArrowUp } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useChatStream } from "@/hooks/useChatStream";
import { useAccount } from "@/hooks/useAccount";
import { useQueryClient } from "@tanstack/react-query";
import { useCreditGate } from "@/stores/useCreditGate";
import { setInFlight, clearInFlight } from "@/lib/inflight";

interface ChatSectionProps {
  initialQuery: string;
  isVisible: boolean;
  projectId?: string | null;
  onArtifactChange?: () => void;
  externalLock?: boolean;
  setBusyPhase?: (p: "idle"|"brainstorm"|"generate"|"chat") => void;
  readOnly?: boolean;
  historyBootstrap?: any[];
  forceDesignOpen?: boolean;
  cadCodeVersion?: number | null;
  brainstormVersion?: number | null;
}

export function ChatSection({
  initialQuery,
  isVisible,
  projectId,
  onArtifactChange,
  externalLock = false,
  setBusyPhase,
  readOnly = false,
  historyBootstrap = [],
  cadCodeVersion,
  brainstormVersion,
}: ChatSectionProps) {
  const {
    messages,
    sendMessage,
    cancel,
    isStreaming,
  } = readOnly
    ? {
        messages: useMemo(() => historyBootstrap, [historyBootstrap]),
        sendMessage: () => {},
        cancel: () => {},
        isStreaming: false,
      }
    : useChatStream({
        projectId,
        initialUserMessage: projectId ? initialQuery : undefined,
        onArtifactChange,
        cadCodeVersion,
        brainstormVersion,
      });

  const [newMessage, setNewMessage] = useState("");
  const [placeholderId, setPlaceholderId] = useState<string | null>(null);
  const [placeholderText, setPlaceholderText] = useState<string>("");
  const showLocalUserBubble = !projectId && !!initialQuery;
  const isComposingInput = useRef(false);
  const { data: me } = useAccount();
  const qc = useQueryClient();
  const openGate = useCreditGate((s) => s.openGate);


  // auto-scroll to bottom when new messages stream in
  const endRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, placeholderText]);

  useEffect(() => {
    if (isStreaming) setBusyPhase?.("chat");
  }, [isStreaming, setBusyPhase]);

  const pendingIdRef = useRef<string | null>(null);

  const handleSendMessage = (e: React.FormEvent) => {
    e.preventDefault();
    const msg = newMessage.trim();
    if (!msg || !projectId || isStreaming || externalLock) return;

    const dailyLeft    = me?.creditsLeft ?? 0;
    const dailyQuota   = me?.dailyQuota ?? 0;
    const creditsToday = me?.creditsToday ?? Math.max(0, dailyQuota - dailyLeft);

    const monthlyCap   = me?.monthlyCreditsCap ?? 0;
    const monthlyUsed  = me?.monthlyCredits ?? 0;
    const monthlyRemaining = Math.max(0, monthlyCap - monthlyUsed);

    const isDailyOut   = dailyLeft <= 0;
    const isMonthlyOut = monthlyCap > 0 && monthlyRemaining <= 0;

    const actuallySend = (text: string) => {
      setNewMessage("");
      if (projectId) setInFlight("codegen", projectId);

      const tempId = `pending-${Date.now()}`;
      pendingIdRef.current = tempId;
      setPlaceholderId(tempId);
      setPlaceholderText("Thinking…");

      const t = setTimeout(() => {
        if (pendingIdRef.current === tempId) {
          setPlaceholderText("Working on it…");
        }
      }, 10_000);

      sendMessage(text, {
        onFirstToken: () => {
          clearTimeout(t);
          if (projectId) clearInFlight("codegen", projectId);
          pendingIdRef.current = null;
          setPlaceholderId(null);
          setPlaceholderText("");
          qc.invalidateQueries({ queryKey: ["me"] });
          qc.invalidateQueries({ queryKey: ["cad", projectId] });
          qc.invalidateQueries({ queryKey: ["versions", projectId] });
        },
        onError: () => {
          clearTimeout(t);
          if (projectId) clearInFlight("codegen", projectId);
          pendingIdRef.current = null;
          setPlaceholderId(null);
          setPlaceholderText("");
        },
      });
    };

    if (isDailyOut || isMonthlyOut) {
      openGate({
        plan: me?.plan,
        limits: {
          dailyQuota,
          creditsLeft: dailyLeft,
          creditsToday,
          monthlyCap,
          monthlyUsed,
          monthlyRemaining,
        },
        banks: {
          rollover: me?.bankRollover ?? 0,
          rewards: (me?.bankRewards ?? me?.creditsBank ?? 0) || 0,
        },
        gateFor: "chat",
        onContinue: () => {
          actuallySend(msg);
        },
      });
      return;
    }

    // Normal path
    actuallySend(msg);
  };


  if (!isVisible) return null;

  const inputDisabled = !projectId || externalLock || isStreaming;

  return (
    <div className="w-[35%] bg-background flex flex-col h-full">
      {/* Messages */}
      <div className="flex-1 overflow-hidden">
        <ScrollArea className="h-full">
          <div className="p-4 space-y-4">
            {showLocalUserBubble && (
              <div className="flex justify-end">
                <div className="max-w-xs lg:max-w-md px-4 py-2 rounded-lg whitespace-pre-wrap break-words bg-primary text-primary-foreground">
                  <p className="text-sm">{initialQuery}</p>
                </div>
              </div>
            )}
            {messages.map((message) => (
              <div
                key={message.id}
                className={`flex ${message.isUser ? "justify-end" : "justify-start"}`}
              >
                <div
                  className={`max-w-xs lg:max-w-md px-4 py-2 rounded-lg whitespace-pre-wrap break-words ${
                    message.isUser
                      ? "bg-primary text-primary-foreground"
                      : "bg-muted text-muted-foreground"
                  }`}
                >
                  <p className="text-sm">{message.content}</p>
                </div>
              </div>
            ))}
            {placeholderId && (
              <div className="flex justify-start">
                <div className="max-w-xs lg:max-w-md px-4 py-2 rounded-lg bg-muted text-muted-foreground">
                  <p className="text-sm">{placeholderText}</p>
                </div>
              </div>
            )}
            <div ref={endRef} />
          </div>
        </ScrollArea>
      </div>

      {/* Input */}
      {readOnly ? (
        <div className="p-4 border-t border-border bg-background text-center text-sm text-muted-foreground">
          Remix this project to continue the conversation.
        </div>
      ) : (
        <div className="p-4 border-t border-border bg-background flex-shrink-0">
          <form onSubmit={handleSendMessage} className="w-full">
            <div className="relative">
              {/* Bubble container (clips to pill) */}
              <div className="relative w-full rounded-2xl border border-primary/20 bg-background shadow-sm overflow-hidden">
                <textarea
                  rows={1}
                  value={newMessage}
                  onChange={(e) => {
                    setNewMessage(e.target.value);

                    // Auto-grow up to 5 lines, then internal scroll
                    const el = e.currentTarget;
                    const cs = window.getComputedStyle(el);
                    const line = parseFloat(cs.lineHeight || "20"); // px
                    const padTop = parseFloat(cs.paddingTop || "0");
                    const padBot = parseFloat(cs.paddingBottom || "0");
                    const maxLines = 5;
                    const maxH = Math.round(line * maxLines + padTop + padBot);

                    el.style.height = "0px";
                    const next = Math.min(el.scrollHeight, maxH);
                    el.style.height = next + "px";
                    el.style.overflowY = el.scrollHeight > maxH ? "auto" : "hidden";
                  }}
                  onCompositionStart={() => (isComposingInput.current = true)}
                  onCompositionEnd={() => (isComposingInput.current = false)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey && !isComposingInput.current) {
                      e.preventDefault();
                      handleSendMessage(e);
                    }
                  }}
                  placeholder={
                    projectId
                      ? (inputDisabled ? "Please wait..." : "Edit or ask anything…")
                      : "Generate a brainstorm to start the chat…"
                  }
                  disabled={inputDisabled}
                  className={[
                    "block w-full bg-transparent border-0 outline-none",
                    "text-sm leading-relaxed",
                    "min-h-[48px]",                 // comfy starting height
                    "pl-5 pr-[4.75rem] py-3",       // left padding + reserved right for the button
                    "resize-none focus:ring-0",
                  ].join(" ")}
                  style={{
                    overflowWrap: "anywhere",       // keep very long strings inside the bubble
                    wordBreak: "break-word",
                  }}
                  aria-label="Chat message"
                  data-gramm="false"
                  data-lt-active="false"
                  spellCheck
                />

                {/* Send button — always centered vertically inside the pill */}
                <button
                  type="submit"
                  disabled={inputDisabled || !newMessage.trim()}
                  className="absolute right-2 top-1/2 -translate-y-1/2 inline-flex h-8 w-8 items-center justify-center rounded-xl bg-primary text-white shadow-md ring-1 ring-black/10 hover:shadow-lg disabled:opacity-50"
                  aria-label="Send"
                  title="Send (Enter) • New line (Shift+Enter)"
                >
                  <ArrowUp className="h-5 w-5" />
                </button>
              </div>
              <div className="mt-2 flex items-start gap-2 text-[10px] text-muted-foreground pl-2" role="note">
                <p className="leading-snug">
                  Makistry can make mistakes. Please double-check responses. 
                </p>
              </div>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}