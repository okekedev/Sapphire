import { useState, useRef, useEffect } from "react";
import { X, Send, Loader2, CheckCircle2 } from "lucide-react";
import { MarkdownMessage } from "@/shared/components/ui/markdown-message";
import { cn } from "@/shared/lib/utils";
import { sendAgentChat } from "@/shared/api/chat";

export function NewLeadDialog({
  businessId,
  onClose,
  onCreated,
}: {
  businessId: string;
  onClose: () => void;
  onCreated: () => void;
}) {
  const [messages, setMessages] = useState<{ role: "user" | "assistant"; content: string }[]>([
    { role: "assistant", content: "Hi, I'm Jordan! Who would you like to add as a new lead? Share their name and phone or email." },
  ]);
  const [input, setInput] = useState("");
  const [threadId, setThreadId] = useState<string | null>(null);
  const [isPending, setIsPending] = useState(false);
  const [created, setCreated] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages]);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const handleSend = async () => {
    const msg = input.trim();
    if (!msg || isPending) return;
    setMessages((prev) => [...prev, { role: "user", content: msg }]);
    setInput("");
    setIsPending(true);
    try {
      const res = await sendAgentChat({
        business_id: businessId,
        agent: "sales",
        message: msg,
        thread_id: threadId,
      });
      if (res.thread_id) setThreadId(res.thread_id);
      setMessages((prev) => [...prev, { role: "assistant", content: res.content }]);
      const lower = res.content.toLowerCase();
      if (!created && (lower.includes("created") || lower.includes("added") || lower.includes("lead has been") || lower.includes("contact has been"))) {
        setCreated(true);
        onCreated();
        setTimeout(() => onClose(), 2500);
      }
    } catch {
      setMessages((prev) => [...prev, { role: "assistant", content: "Something went wrong. Please try again." }]);
    } finally {
      setIsPending(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative w-full max-w-md rounded-xl border border-border bg-card shadow-2xl overflow-hidden flex flex-col max-h-[80vh]">
        <div className="flex items-center justify-between px-4 py-3 border-b border-border bg-muted/30 shrink-0">
          <div>
            <p className="text-sm font-semibold">New Lead</p>
            <p className="text-[11px] text-muted-foreground">Jordan · Sales AI</p>
          </div>
          <button type="button" onClick={onClose} className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors">
            <X size={14} />
          </button>
        </div>

        <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-3">
          {messages.map((msg, i) => (
            <div key={i} className={cn("flex", msg.role === "user" ? "justify-end" : "justify-start")}>
              <div className={cn(
                "rounded-xl px-3 py-2 text-xs max-w-[90%] leading-relaxed",
                msg.role === "user" ? "bg-primary text-primary-foreground" : "bg-muted text-foreground",
              )}>
                {msg.role === "assistant" ? <MarkdownMessage content={msg.content} /> : msg.content}
              </div>
            </div>
          ))}
          {isPending && (
            <div className="flex justify-start">
              <div className="rounded-xl px-3 py-2 bg-muted text-xs text-muted-foreground flex items-center gap-1.5">
                <Loader2 size={10} className="animate-spin" /> Thinking…
              </div>
            </div>
          )}
          {created && (
            <div className="flex justify-center">
              <div className="rounded-full bg-emerald-100 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-300 px-3 py-1 text-xs font-medium flex items-center gap-1.5">
                <CheckCircle2 size={12} /> Lead created — closing…
              </div>
            </div>
          )}
        </div>

        {!created && (
          <form onSubmit={(e) => { e.preventDefault(); handleSend(); }} className="border-t border-border p-3 flex gap-2 shrink-0">
            <input
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="e.g. John Smith, 555-1234…"
              className="flex-1 rounded-lg border border-border bg-background px-3 py-1.5 text-xs outline-none focus:border-primary transition-colors"
              disabled={isPending}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
            />
            <button
              type="submit"
              disabled={!input.trim() || isPending}
              className="rounded-lg bg-primary px-3 py-1.5 text-primary-foreground disabled:opacity-40 hover:bg-primary/90 transition-colors"
            >
              <Send size={12} />
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
