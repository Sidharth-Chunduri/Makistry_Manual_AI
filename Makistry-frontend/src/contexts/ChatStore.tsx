import React, {
  createContext,
  useContext,
  useState,
  useCallback,
} from "react";
import { api } from "@/lib/api"; 
/* ------------------------------------------------------------------ */
/* Types                                                              */
/* ------------------------------------------------------------------ */

export interface ChatMessage {
  id: string;
  content: string;
  isUser: boolean;
}

type ChatMap = Record<string, ChatMessage[]>;

interface ChatCtx {
  chats: ChatMap;
  setChats: React.Dispatch<React.SetStateAction<ChatMap>>;
}

/* ------------------------------------------------------------------ */
/* Context Provider                                                    */
/* ------------------------------------------------------------------ */

const ChatContext = createContext<ChatCtx | null>(null);

export function ChatProvider({ children }: { children: React.ReactNode }) {
  const [chats, setChats] = useState<ChatMap>({});
  return (
    <ChatContext.Provider value={{ chats, setChats }}>
      {children}
    </ChatContext.Provider>
  );
}

/* ------------------------------------------------------------------ */
/* Hook: project-scoped chat access                                    */
/* ------------------------------------------------------------------ */

type ProjectId = string | null | undefined;

export function useChatStore(projectId: ProjectId) {
  const ctx = useContext(ChatContext);
  if (!ctx) throw new Error("ChatProvider missing");
  const { chats, setChats } = ctx;

  // stable key even if no project yet
  const key = projectId ?? "_noproj";

  const messages = chats[key] ?? [];

  // generic updater (same signature you had before)
  const setMessages = useCallback(
    (fn: (prev: ChatMessage[]) => ChatMessage[]) => {
      setChats((all) => ({ ...all, [key]: fn(all[key] ?? []) }));
    },
    [key, setChats],
  );

  /* ---------- convenience appenders ---------- */
  const appendAssistant = useCallback(
    (text: string) => {
      if (!text) return;
      const id = crypto.randomUUID();
      setMessages((prev) => [...prev, { id, content: text, isUser: false }]);
    },
    [setMessages],
  );

  const appendUser = useCallback(
    (text: string) => {
      if (!text) return;
      const id = crypto.randomUUID();
      setMessages((prev) => [...prev, { id, content: text, isUser: true }]);
    },
    [setMessages],
  );

  const loadHistory = useCallback(async () => {
    if (!projectId) return;
    try {
      const resp = await api.get<any[]>(
        `/chat/history?project_id=${encodeURIComponent(projectId)}`
      );
      // map Firestore docs → ChatMessage[]
      const mapped: ChatMessage[] = resp.data.map((m: any) => ({
        id:      m.id ?? crypto.randomUUID(),
        content: m.content,
        isUser:  (m.role ?? "assistant") === "user",
      }));
      setChats((all) => ({ ...all, [key]: mapped }));
    } catch (err) {
      console.error("loadHistory failed", err);
    }
  }, [projectId, key, setChats]);

  return { messages, setMessages, appendAssistant, appendUser, loadHistory };
}
