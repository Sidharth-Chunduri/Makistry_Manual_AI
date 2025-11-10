"use client";

import { useRef, useEffect, useState } from "react";
import { useBrainstorm, type BrainstormResp } from "@/hooks/useBrainstorm";
import { toast } from "sonner";

// Lightweight, inline auto-resize textarea
function AutoResizeTextarea({
  value,
  onChange,
  placeholder,
  disabled,
  className = "",
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
}) {
  const ref = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "0px";             // reset
    el.style.height = Math.min(el.scrollHeight, 192) + "px"; // cap ~12rem
  }, [value]);

  return (
    <textarea
      ref={ref}
      rows={1}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      disabled={disabled}
      className={
        [
          "flex-1 rounded-2xl border border-primary/20 bg-background",
          "p-4 text-base leading-relaxed resize-none",
          "focus:outline-none focus:ring-2 focus:ring-primary/30",
          "max-h-48 overflow-auto whitespace-pre-wrap break-words",
          className,
        ].join(" ")
      }
      aria-label="Describe your idea"
    />
  );
}

export default function PromptForm({
  onSuccess,
}: {
  onSuccess: (data: BrainstormResp) => void;
}) {
  const [prompt, setPrompt] = useState("");
  const brainstormMutation = useBrainstorm();

  const submit = async () => {
    if (!prompt.trim()) {
      toast.error("Prompt can’t be empty");
      return;
    }
    try {
      const data = await brainstormMutation.mutateAsync(prompt);
      console.log("💡 Brainstorm response:", data);
      onSuccess(data);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Unknown error";
      toast.error(msg);
    }
  };

  return (
    <div className="flex items-end gap-2">
      <AutoResizeTextarea
        value={prompt}
        onChange={setPrompt}
        placeholder="Describe your idea…"
        disabled={brainstormMutation.isPending}
      />
      <button
        onClick={submit}
        disabled={brainstormMutation.isPending}
        className="rounded-xl bg-indigo-600 px-4 py-2 text-white disabled:opacity-50"
      >
        {brainstormMutation.isPending ? "Thinking…" : "Go"}
      </button>
    </div>
  );
}
