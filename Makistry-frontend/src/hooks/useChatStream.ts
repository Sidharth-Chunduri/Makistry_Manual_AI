// useChatStream.ts
import { useCallback, useRef, useState, useEffect } from "react";
import { chatStream } from "@/lib/api/chatStream";
import { useChatStore, ChatMessage } from "@/contexts/ChatStore";
import { useQueryClient } from "@tanstack/react-query"

interface UseChatStreamArgs {
  projectId: string | null | undefined;
  initialUserMessage?: string;
  initialAssistantMessage?: string;
  onArtifactChange?: () => void;
  cadCodeVersion?: number | null;
  brainstormVersion?: number | null;
}

type SendOptions = {
  onFirstToken?: () => void;
  onError?: (err: unknown) => void;
};

export function useChatStream({
  projectId,
  initialUserMessage,
  initialAssistantMessage,
  onArtifactChange,
  cadCodeVersion,
  brainstormVersion,
}: UseChatStreamArgs) {
  const { messages, setMessages } = useChatStore(projectId);
  const [isStreaming, setIsStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const queryClient = useQueryClient();

  // Seed once (only if no messages yet)
  useEffect(() => {
    if (!projectId) return;
    if (messages.length > 0) return;
    const init: ChatMessage[] = [];
    if (initialUserMessage) {
      init.push({ id: "init-u", content: initialUserMessage, isUser: true });
    }
    if (initialAssistantMessage) {
      init.push({ id: "init-a", content: initialAssistantMessage, isUser: false });
    }
    if (init.length && messages.length === 0) {
      setMessages(() => init);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]); // deliberately ignore messages, setMessages to avoid reseeding

  const sendMessage = useCallback(
    async (text: string, opts?: SendOptions) => {
      if (!projectId) return;

      const userId = crypto.randomUUID();
      setMessages((m) => [...m, { id: userId, content: text, isUser: true }]);

      const asstId = crypto.randomUUID();

      abortRef.current?.abort();
      const ctrl = new AbortController();
      abortRef.current = ctrl;
      setIsStreaming(true);
      
      let seenFirst = false;
      try {
        await chatStream({
          projectId,
          message: text,
          cadCodeVersion,
          brainstormVersion,
          signal: ctrl.signal,
          onChunk: (chunk) => {
            // Ignore server keepalives (zero-width char)
            if (chunk === "\u2063") return;

            if (!seenFirst) {
              seenFirst = true;
              opts?.onFirstToken?.();
              setMessages((m) => [
                ...m,
                { id: asstId, content: chunk, isUser: false },
              ]);
            } else {
              setMessages((m) =>
                m.map((msg) =>
                  msg.id === asstId ? { ...msg, content: msg.content + chunk } : msg,
                ),
              );
            }
          },
        });
        onArtifactChange?.();
        if (projectId) {
          queryClient.invalidateQueries({ queryKey: ["brainstorm", projectId] });
          queryClient.invalidateQueries({ queryKey: ["cad", projectId] })
        }
      } catch (err) {
        opts?.onError?.(err);
        console.error("chatStream error", err);
        setMessages((m) =>
          m.map((msg) =>
            msg.id === asstId
              ? { ...msg, content: msg.content + "\n\n⚠ Error contacting assistant." }
              : msg,
          ),
        );
      } finally {
        setIsStreaming(false);
      }
    },
    [projectId, setMessages, onArtifactChange, cadCodeVersion, brainstormVersion],
  );

  const cancel = useCallback(() => {
    abortRef.current?.abort();
    setIsStreaming(false);
  }, []);

  return { messages, sendMessage, cancel, isStreaming };
}
