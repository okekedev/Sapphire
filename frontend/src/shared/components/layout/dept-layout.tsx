/**
 * DeptLayout — shared layout for all department pages.
 *
 * Renders:
 *   [sub-nav pill bar]  [Ask AI button]
 *   ─────────────────────────────────────────
 *   [active section content]  │  [chat panel]
 *
 * Chat panel is toggled open/closed and sticks to viewport.
 */
import { useState, useRef, useEffect, useCallback } from "react";
import { MessageSquare, X, Send, Loader2, ChevronDown } from "lucide-react";
import { useMutation } from "@tanstack/react-query";
import { cn } from "@/shared/lib/utils";
import { MarkdownMessage } from "@/shared/components/ui/markdown-message";
import { sendAgentChat } from "@/shared/api/chat";

export interface DeptSection {
  id: string;
  label: string;
  icon: React.ReactNode;
  content: React.ReactNode;
  /** Optional count/label shown as a badge on the pill. */
  badge?: string | number;
  /** When true, tab is greyed out and non-clickable. */
  disabled?: boolean;
  /** Tooltip shown on hover when disabled. */
  disabledReason?: string;
}

interface DeptLayoutProps {
  sections: DeptSection[];
  /** Which section is shown first. Defaults to sections[0]. */
  defaultSection?: string;
  /** The Foundry agent name for this department's chat panel. */
  agentName?: string; // "admin" | "billing" | "marketing" | "operations" | "sales"
  businessId: string;
  /**
   * When set, the chat panel opens and sends this message automatically.
   * The parent should clear it via onPendingConsumed.
   */
  pendingMessage?: string | null;
  onPendingConsumed?: () => void;
}

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export function DeptLayout({
  sections,
  defaultSection,
  agentName,
  businessId,
  pendingMessage,
  onPendingConsumed,
}: DeptLayoutProps) {
  const [active, setActive] = useState(defaultSection ?? sections[0]?.id ?? "");
  const [chatOpen, setChatOpen] = useState(false);
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

  // Handle programmatic message from parent (e.g. "ask agent to do X")
  useEffect(() => {
    if (pendingMessage && agentName) {
      setChatOpen(true);
      setInput(pendingMessage);
      onPendingConsumed?.();
      // Send after a tick so the input is populated
      setTimeout(() => {
        sendMsg(pendingMessage);
        setInput("");
      }, 50);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingMessage]);

  const mutation = useMutation({
    mutationFn: (msg: string) =>
      sendAgentChat({
        business_id: businessId,
        agent: agentName!,
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
      if (!msg.trim() || mutation.isPending || !agentName) return;
      mutation.mutate(msg);
    },
    [mutation, agentName],
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

  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const activeSection = sections.find((s) => s.id === active);

  // Close dropdown on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    }
    if (menuOpen) document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [menuOpen]);

  return (
    <div className="flex flex-col gap-0">
      {/* ── Sub-nav dropdown ── */}
      <div className="flex items-center gap-2 mb-5">
        <div ref={menuRef} className="relative">
          <button
            type="button"
            onClick={() => setMenuOpen((v) => !v)}
            className="flex items-center gap-2 rounded-lg border border-border bg-card px-3 py-2 text-sm font-medium shadow-sm hover:bg-muted/50 transition-colors"
          >
            <span className="[&>svg]:size-[14px] text-muted-foreground">{activeSection?.icon}</span>
            <span>{activeSection?.label}</span>
            {activeSection?.badge != null && activeSection.badge !== 0 && (
              <span className="min-w-[18px] rounded-full bg-muted-foreground/15 px-1.5 py-0.5 text-[10px] font-semibold tabular-nums leading-none text-muted-foreground">
                {activeSection.badge}
              </span>
            )}
            <ChevronDown size={13} className={cn("text-muted-foreground transition-transform duration-150", menuOpen && "rotate-180")} />
          </button>

          {menuOpen && (
            <div className="absolute left-0 top-full mt-1.5 z-30 min-w-[200px] rounded-xl border border-border bg-card shadow-lg overflow-hidden">
              {sections.map((section) => (
                <button
                  key={section.id}
                  type="button"
                  disabled={section.disabled}
                  title={section.disabled ? section.disabledReason : undefined}
                  onClick={() => {
                    if (!section.disabled) {
                      setActive(section.id);
                      setMenuOpen(false);
                    }
                  }}
                  className={cn(
                    "w-full flex items-center gap-2.5 px-3.5 py-2.5 text-sm transition-colors",
                    section.disabled
                      ? "opacity-40 cursor-not-allowed text-muted-foreground"
                      : active === section.id
                        ? "bg-primary/8 text-primary font-medium"
                        : "text-foreground hover:bg-muted",
                  )}
                >
                  <span className="[&>svg]:size-[14px] text-muted-foreground shrink-0">{section.icon}</span>
                  {section.label}
                  {section.badge != null && section.badge !== 0 && (
                    <span className="ml-auto min-w-[18px] rounded-full bg-muted-foreground/15 px-1.5 py-0.5 text-[10px] font-semibold tabular-nums leading-none text-muted-foreground">
                      {section.badge}
                    </span>
                  )}
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="flex-1" />

        {agentName && (
          <button
            type="button"
            onClick={() => setChatOpen((v) => !v)}
            className={cn(
              "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
              chatOpen
                ? "bg-primary/10 text-primary border border-primary/20"
                : "text-muted-foreground hover:text-foreground hover:bg-muted",
            )}
          >
            <MessageSquare size={14} />
            Ask AI
          </button>
        )}
      </div>

      {/* ── Content + Chat ── */}
      <div className="flex gap-5 items-start">
        {/* Section content */}
        <div className="flex-1 min-w-0">
          {activeSection?.content}
        </div>

        {/* Chat panel — sticky to viewport top */}
        {chatOpen && agentName && (
          <div className="w-[340px] shrink-0 flex flex-col rounded-xl border border-border bg-card sticky top-6 max-h-[calc(100vh-96px)] overflow-hidden shadow-sm">
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-2.5 border-b border-border bg-muted/30 shrink-0">
              <div>
                <p className="text-xs font-semibold capitalize">{agentName} AI</p>
                <p className="text-[10px] text-muted-foreground">Department assistant</p>
              </div>
              <button
                type="button"
                onClick={() => setChatOpen(false)}
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
                <div className="flex h-full min-h-[160px] items-center justify-center">
                  <p className="text-center text-[11px] text-muted-foreground px-4 leading-relaxed">
                    Ask anything about this workspace.
                  </p>
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
                placeholder="Message AI…"
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
      </div>
    </div>
  );
}
