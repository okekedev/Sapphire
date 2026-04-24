import { useState, useRef, useEffect, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Send, Loader2 } from "lucide-react";
import { cn } from "@/shared/lib/utils";
import { useAppStore } from "@/shared/stores/app-store";
import { getCompanyProfile, saveCompanyProfile } from "@/shared/api/businesses";
import { sendAgentChat } from "@/shared/api/chat";
import { MarkdownMessage } from "@/shared/components/ui/markdown-message";
import { Spinner } from "@/shared/components/ui/spinner";

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}


export default function NarrativePage() {
  const business = useAppStore((s) => s.activeBusiness);
  const bizId = business?.id ?? "";
  const queryClient = useQueryClient();

  // ── Narrative (right panel) ──
  const { data: profile, isLoading } = useQuery({
    queryKey: ["company-profile", bizId],
    queryFn: () => getCompanyProfile(bizId),
    enabled: !!bizId,
  });

  const [draft, setDraft] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (profile) setDraft(profile.narrative ?? "");
  }, [profile]);

  useEffect(() => {
    const el = textareaRef.current;
    if (el) {
      el.style.height = "auto";
      el.style.height = `${el.scrollHeight}px`;
    }
  }, [draft]);

  const saveMutation = useMutation({
    mutationFn: (text: string) =>
      saveCompanyProfile(bizId, { narrative: text }),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["company-profile", bizId] }),
  });

  const handleBlur = () => {
    if (draft !== (profile?.narrative ?? "")) {
      saveMutation.mutate(draft);
    }
  };

  // ── Chat (left panel) ──
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [threadId, setThreadId] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const chatMutation = useMutation({
    mutationFn: (msg: string) =>
      sendAgentChat({ business_id: bizId, agent: "james", message: msg, thread_id: threadId }),
    onSuccess: (data) => {
      if (data.thread_id) setThreadId(data.thread_id);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: data.content },
      ]);
      // Refresh narrative in case James updated it
      queryClient.invalidateQueries({ queryKey: ["company-profile", bizId] });
    },
    onError: () => {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "Something went wrong — is the backend running?" },
      ]);
    },
  });

  const sendMsg = useCallback(
    (msg: string) => {
      if (!msg.trim() || chatMutation.isPending || !bizId) return;
      // Add user message immediately so there's visible feedback
      setMessages((prev) => [...prev, { role: "user", content: msg }]);
      chatMutation.mutate(msg);
    },
    [chatMutation, bizId],
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

  return (
    <div className="p-4 md:p-6 md:h-[calc(100vh-3.5rem)] flex flex-col">
    <div className="flex flex-col md:flex-row gap-5 flex-1 min-h-0">

      {/* ── Left: Business Narrative ── */}
      <div className="flex flex-col flex-1 min-h-[320px] rounded-xl border border-border bg-card overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3 border-b border-border shrink-0">
          <p className="text-sm font-semibold">Business Narrative</p>
          {saveMutation.isPending && (
            <span className="text-[11px] text-muted-foreground">Saving…</span>
          )}
        </div>

        {isLoading ? (
          <div className="flex flex-1 items-center justify-center">
            <Spinner className="h-5 w-5" />
          </div>
        ) : (
          <textarea
            ref={textareaRef}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={handleBlur}
            placeholder="Type here..."
            className={cn(
              "flex-1 w-full bg-transparent px-5 py-4 text-sm leading-relaxed",
              "placeholder:text-muted-foreground/40 resize-none",
              "focus:outline-none",
            )}
          />
        )}
      </div>

      {/* ── Right: Chat ── */}
      <div className="flex flex-col min-h-[420px] md:w-[400px] md:shrink-0 rounded-xl border border-border bg-card overflow-hidden">
        <div className="px-4 py-3 border-b border-border shrink-0">
          <p className="text-sm font-semibold">James — Basic Assistant</p>
        </div>

        <div ref={scrollRef} className="flex-1 overflow-y-auto p-3 space-y-2">
          {messages.length === 0 && !chatMutation.isPending && (
            <div className="flex h-full items-center justify-center py-6">
              <p className="text-center text-[11px] text-muted-foreground px-4 leading-relaxed">
                James can search the web and research your business. Use this chat to build and update your narrative.
              </p>
            </div>
          )}
          {messages.map((msg, i) => (
            <div
              key={i}
              className={cn("flex", msg.role === "user" ? "justify-end" : "justify-start")}
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
          {chatMutation.isPending && (
            <div className="flex justify-start">
              <div className="rounded-xl px-3 py-2 bg-muted text-xs text-muted-foreground flex items-center gap-1.5">
                <Loader2 size={10} className="animate-spin" />
                <span>Thinking…</span>
              </div>
            </div>
          )}
        </div>

        <form
          onSubmit={handleSubmit}
          className="border-t border-border p-2 flex gap-1.5 shrink-0"
        >
          <input
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Type here..."
            className="flex-1 rounded-lg border border-border bg-background px-2.5 py-1.5 text-xs outline-none focus:border-primary transition-colors"
            disabled={chatMutation.isPending}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSubmit();
              }
            }}
          />
          <button
            type="submit"
            disabled={!input.trim() || chatMutation.isPending}
            className="rounded-lg bg-primary px-2.5 py-1.5 text-primary-foreground disabled:opacity-40 hover:bg-primary/90 transition-colors shrink-0"
          >
            <Send size={12} />
          </button>
        </form>
      </div>

    </div>
    </div>
  );
}
