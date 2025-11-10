// src/lib/api/chatStream.ts
import { getBearerHeader } from "@/lib/tokenManager";
import { getApiBase } from "@/lib/api";

export interface ChatStreamOptions {
  baseUrl?: string;          // e.g. import.meta.env.VITE_API_URL
  projectId: string;
  message: string;
  onChunk?: (text: string) => void;
  signal?: AbortSignal;
  cadCodeVersion?: number | null;
  brainstormVersion?: number | null;
}

/**
 * Stream assistant reply text from backend /chat.
 * Backend returns raw text chunks (chunked transfer).
 */
export async function chatStream({
  baseUrl = getApiBase(),
  projectId,
  message,
  onChunk,
  signal,
  cadCodeVersion,
  brainstormVersion,
}: ChatStreamOptions): Promise<string> {
  const headers = {
    "Content-Type": "application/json",
    ...(await getBearerHeader()),
  } as Record<string, string>;

  const resp = await fetch(`${String(baseUrl).replace(/\/$/, "")}/chat`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      project_id: projectId,
      user_query: message,
      ...(typeof cadCodeVersion === "number" ? { cad_code_version: cadCodeVersion } : {}),
      ...(typeof brainstormVersion === "number" ? { brainstorm_version: brainstormVersion } : {}),
    }),
    credentials: "include",
    signal,
  });

  if (!resp.ok || !resp.body) {
    const txt = await resp.text().catch(() => "");
    throw new Error(`Chat request failed (${resp.status}): ${txt}`);
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let full = "";
  let done = false;

  while (!done) {
    const { value, done: d } = await reader.read();
    done = d;
    if (value) {
      const chunk = decoder.decode(value, { stream: !done });
      full += chunk;
      onChunk?.(chunk);
    }
  }

  return full;
}
