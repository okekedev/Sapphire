/**
 * JamesChat — floating bottom-right help button and chat panel.
 *
 * James is the Home page assistant and app guide for Sapphire.
 * Available on all authenticated pages as a floating button.
 */
import { useState, useRef, useEffect, useCallback } from "react";
import { MessageSquare, X, Send, Loader2 } from "lucide-react";
import { useMutation } from "@tanstack/react-query";
import { cn } from "@/shared/lib/utils";
import { MarkdownMessage } from "@/shared/components/ui/markdown-message";
import { sendAgentChat } from "@/shared/api/chat";
import { useAppStore } from "@/shared/stores/app-store";

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

const SUGGESTION_CHIPS = [
  "Help me complete my business narrative",
  "Add contacts",
  "Add jobs",
];

export function JamesChat() {
  const { activeBusiness } = useAppStore();
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [threadId, setThreadId] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  // Focus input when panel opens
  useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [open]);

  const businessId = activeBusiness?.id ?? "";

  const mutation = useMutation({
    mutationFn: (msg: string) =>
      sendAgentChat({
        business_id: businessId,
        agent: "james",
        message: msg,
        thread_id: threadId,
      }),
    onSuccess: (data, msg) => {
      if (data.thread_id) setThreadId(data.thread_id);
      setMessages((prev) => [
        ...prev,
        { role: "user", content: msg },
        { role: "assistant", content: data.content },
      ]);
    },
  });

  const sendMsg = useCallback(
    (msg: string) => {
      if (!msg.trim() || mutation.isPending || !businessId) return;
      mutation.mutate(msg);
    },
    [mutation, businessId],
  );

  const handleSubmit = useCallback(
    (e?: React.FormEvent) => {
      e?.preventDefault();
      const msg = input.trim();
      if (!msg) return;
      sendMsg(msg);
      setInput("");
    },
    [input, sendMsg],
  );

  const handleChip = useCallback(
    (chip: string) => {
      sendMsg(chip);
    },
    [sendMsg],
  );

  if (!businessId) return null;

  return (
    <div className="fixed bottom-5 right-5 z-50 flex flex-col items-end gap-3">
      {/* Chat panel */}
      {open && (
        <div className="w-[360px] max-h-[480px] flex flex-col rounded-xl border border-border bg-card shadow-lg overflow-hidden">
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-2.5 border-b border-border bg-muted/30 shrink-0">
            <div>
              <p className="text-xs font-semibold">James</p>
              <p className="text-[10px] text-muted-foreground">Sapphire assistant</p>
            </div>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
            >
              <X size={13} />
            </button>
          </div>

          {/* Messages */}
          <div
            ref={scrollRef}
            className="flex-1 overflow-y-auto p-3 space-y-2 min-h-[200px]"
          >
            {messages.length === 0 && !mutation.isPending && (
              <div className="flex flex-col h-full min-h-[160px] items-center justify-center gap-3">
                <p className="text-center text-[11px] text-muted-foreground px-4 leading-relaxed">
                  Ask me anything about Sapphire or your company profile.
                </p>
                {/* Suggestion chips */}
                <div className="flex flex-wrap gap-1.5 justify-center px-2">
                  {SUGGESTION_CHIPS.map((chip) => (
                    <button
                      key={chip}
                      type="button"
                      onClick={() => handleChip(chip)}
                      disabled={mutation.isPending}
                      className="rounded-full border border-border bg-background px-2.5 py-1 text-[10px] text-muted-foreground hover:text-foreground hover:border-primary/40 hover:bg-muted transition-colors disabled:opacity-40"
                    >
                      {chip}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {messages.map((msg, i) => (
              <div
                key={i}
                className={cn(
                  "flex",
                  msg.role === "user" ? "justify-end" : "justify-start",
                )}
              >
                <div
                  className={cn(
                    "rounded-xl px-3 py-2 text-xs max-w-[88%] leading-relaxed",
                    msg.role === "user"
                      ? "bg-primary text-primary-foreground"
                      : "bg-muted text-foreground",
                  )}
                >
                  {msg.role === "assistant" ? (
                    <MarkdownMessage content={msg.content} />
                  ) : (
                    msg.content
                  )}
                </div>
              </div>
            ))}
            {mutation.isPending && (
              <div className="flex justify-start">
                <div className="rounded-xl px-3 py-2 bg-muted text-xs text-muted-foreground flex items-center gap-1.5">
                  <Loader2 size={10} className="animate-spin" />
                  <span>Thinking…</span>
                </div>
              </div>
            )}
          </div>

          {/* Input */}
          <form
            onSubmit={handleSubmit}
            className="border-t border-border p-2 flex gap-1.5 shrink-0"
          >
            <input
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask James…"
              className="flex-1 rounded-lg border border-border bg-background px-2.5 py-1.5 text-xs outline-none focus:border-primary transition-colors"
              disabled={mutation.isPending}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSubmit();
                }
              }}
            />
            <button
              type="submit"
              disabled={!input.trim() || mutation.isPending}
              className="rounded-lg bg-primary px-2.5 py-1.5 text-primary-foreground disabled:opacity-40 hover:bg-primary/90 transition-colors shrink-0"
            >
              <Send size={12} />
            </button>
          </form>
        </div>
      )}

      {/* Floating button */}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={cn(
          "flex h-12 w-12 items-center justify-center rounded-full shadow-lg transition-all",
          open
            ? "bg-primary/90 text-primary-foreground scale-95"
            : "bg-primary text-primary-foreground hover:bg-primary/90 hover:scale-105",
        )}
        title="Ask James"
      >
        {open ? <X size={20} /> : <MessageSquare size={20} />}
      </button>
    </div>
  );
}
