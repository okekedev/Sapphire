import { useState, useRef, useEffect, useCallback } from "react";
import { X, Building2, Loader2, Send, ArrowRight, AlertTriangle, RefreshCw } from "lucide-react";
import { MarkdownMessage } from "@/shared/components/ui/markdown-message";
import { cn } from "@/shared/lib/utils";
import {
  sendOnboardingMessage,
  type SeedInfo,
  type OnboardingMessage,
} from "@/shared/api/businesses";
import { ClaudeTerminalModal } from "@/shared/components/terminal/claude-terminal-modal";

interface CompanyProfileModalProps {
  isOpen: boolean;
  onClose: () => void;
  businessId: string;
  onSaved?: () => void;
}

type Phase = "seed" | "chat";

export function CompanyProfileModal({
  isOpen,
  onClose,
  businessId,
  onSaved,
}: CompanyProfileModalProps) {
  const [phase, setPhase] = useState<Phase>("seed");
  const [employeeName, setEmployeeName] = useState("Assistant");
  const [employeeTitle, setEmployeeTitle] = useState("");

  const [seed, setSeed] = useState<SeedInfo>({
    company_name: "",
    phone: "",
    city: "",
    industry: "",
    website: "",
    socials: "",
  });

  const [messages, setMessages] = useState<OnboardingMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [profileDone, setProfileDone] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null); // "token_expired" | "not_connected"
  const [showTerminal, setShowTerminal] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const seedInfoRef = useRef<SeedInfo | null>(null);
  const lastMessageRef = useRef<{ msg: string; isFirst: boolean } | null>(null);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  useEffect(() => {
    if (phase === "chat" && !loading) {
      inputRef.current?.focus();
    }
  }, [phase, loading]);

  const sendMessage = useCallback(
    async (userMsg: string, isFirst = false) => {
      setLoading(true);
      setAuthError(null);
      lastMessageRef.current = { msg: userMsg, isFirst };

      const updatedMessages: OnboardingMessage[] = [
        ...messages,
        { role: "user" as const, content: userMsg },
      ];
      setMessages(updatedMessages);
      setInput("");

      try {
        const res = await sendOnboardingMessage(
          businessId,
          userMsg,
          isFirst ? [] : messages,
          isFirst ? seedInfoRef.current ?? undefined : undefined,
        );

        // Update employee info from response
        if (res.employee_name) {
          setEmployeeName(res.employee_name);
        }
        if (res.employee_title) {
          setEmployeeTitle(res.employee_title);
        }

        // Check for auth errors from the backend
        if (res.auth_error && res.auth_error_type) {
          setAuthError(res.auth_error_type);
          // Don't add the error message to chat — we'll show a banner instead
          // Remove the user message we just added since it wasn't processed
          setMessages(messages);
          return;
        }

        setMessages((prev) => [
          ...prev,
          { role: "assistant" as const, content: res.response },
        ]);

        if (res.onboarding_complete) {
          setProfileDone(true);
        }
      } catch {
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant" as const,
            content:
              "Sorry, I had trouble connecting. Please try sending your message again.",
          },
        ]);
      } finally {
        setLoading(false);
      }
    },
    [businessId, messages],
  );

  const handleReconnectSuccess = useCallback(() => {
    setShowTerminal(false);
    setAuthError(null);
    // Auto-retry the last message after reconnecting
    if (lastMessageRef.current) {
      const { msg, isFirst } = lastMessageRef.current;
      sendMessage(msg, isFirst);
    }
  }, [sendMessage]);

  const handleStartChat = useCallback(() => {
    const hasName = seed.company_name.trim();
    const hasPhone = seed.phone.trim();
    const hasWebOrSocial = seed.website.trim() || seed.socials.trim();
    if (!hasName || !hasPhone || !hasWebOrSocial) return;

    seedInfoRef.current = seed;
    setPhase("chat");

    const parts = [`My company is ${seed.company_name.trim()}.`];
    if (seed.phone) parts.push(`Phone: ${seed.phone}.`);
    if (seed.city) parts.push(`Based in ${seed.city}.`);
    if (seed.industry) parts.push(`Industry: ${seed.industry}.`);
    if (seed.website) parts.push(`Website: ${seed.website}.`);
    if (seed.socials) parts.push(`Socials: ${seed.socials}.`);
    parts.push("Please research us and build our company profile.");

    sendMessage(parts.join(" "), true);
  }, [seed, sendMessage]);

  const handleSendChat = useCallback(() => {
    if (!input.trim() || loading) return;
    sendMessage(input.trim());
  }, [input, loading, sendMessage]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSendChat();
    }
  };

  if (!isOpen) return null;

  const hasWebOrSocial = seed.website.trim() || seed.socials.trim();
  const canSubmit =
    seed.company_name.trim() && seed.phone.trim() && hasWebOrSocial;

  // Display name — use employee name once known, fall back to generic
  const displayName = employeeName || "your team";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="relative mx-4 flex h-[600px] w-full max-w-2xl flex-col overflow-hidden rounded-xl border border-border bg-background shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-amber-100 dark:bg-amber-900/30">
              <Building2 className="h-5 w-5 text-amber-700 dark:text-amber-400" />
            </div>
            <div>
              <h2 className="text-lg font-semibold">Company Profile</h2>
              <p className="text-sm text-muted-foreground">
                {phase === "seed"
                  ? "Give us a few details to get started"
                  : `${displayName} is researching your business`}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded p-1 text-muted-foreground hover:text-foreground"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {phase === "seed" ? (
          <SeedForm
            seed={seed}
            onChange={setSeed}
            onSubmit={handleStartChat}
            canSubmit={!!canSubmit}
            hasWebOrSocial={!!hasWebOrSocial}
          />
        ) : (
          <ChatView
            employeeName={displayName}
            messages={messages}
            loading={loading}
            profileDone={profileDone}
            authError={authError}
            onReconnect={() => setShowTerminal(true)}
            input={input}
            onInputChange={setInput}
            onSend={handleSendChat}
            onKeyDown={handleKeyDown}
            onDone={() => {
              onSaved?.();
              onClose();
            }}
            chatEndRef={chatEndRef}
            inputRef={inputRef}
          />
        )}
      </div>

      {/* Terminal modal for reconnecting */}
      <ClaudeTerminalModal
        isOpen={showTerminal}
        onClose={() => setShowTerminal(false)}
        businessId={businessId}
        onAuthenticated={handleReconnectSuccess}
      />
    </div>
  );
}

// ── Seed Form ──

function SeedForm({
  seed,
  onChange,
  onSubmit,
  canSubmit,
  hasWebOrSocial,
}: {
  seed: SeedInfo;
  onChange: (s: SeedInfo) => void;
  onSubmit: () => void;
  canSubmit: boolean;
  hasWebOrSocial: boolean;
}) {
  const update = (key: keyof SeedInfo, value: string) =>
    onChange({ ...seed, [key]: value });

  return (
    <>
      <div className="flex-1 overflow-y-auto px-6 py-5">
        <div className="space-y-4">
          {/* Required fields */}
          <div>
            <label className="mb-1 block text-sm font-medium">
              Business name <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={seed.company_name}
              onChange={(e) => update("company_name", e.target.value)}
              placeholder="Acme Corp"
              className={cn(
                "w-full rounded-lg border bg-background px-3 py-2 text-sm",
                "placeholder:text-muted-foreground/50",
                "focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500",
              )}
              onKeyDown={(e) => {
                if (e.key === "Enter" && canSubmit) onSubmit();
              }}
            />
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium">
              Phone number <span className="text-red-500">*</span>
            </label>
            <input
              type="tel"
              value={seed.phone}
              onChange={(e) => update("phone", e.target.value)}
              placeholder="(555) 123-4567"
              className={cn(
                "w-full rounded-lg border bg-background px-3 py-2 text-sm",
                "placeholder:text-muted-foreground/50",
                "focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500",
              )}
              onKeyDown={(e) => {
                if (e.key === "Enter" && canSubmit) onSubmit();
              }}
            />
          </div>

          {/* Website or social — at least one required */}
          <div className="rounded-lg border border-dashed border-amber-300 bg-amber-50/50 p-4 dark:border-amber-800 dark:bg-amber-950/20">
            <p className="mb-3 text-xs font-medium text-amber-700 dark:text-amber-400">
              At least one required — so we can verify your business
            </p>
            <div className="space-y-3">
              <div>
                <label className="mb-1 block text-sm font-medium">Website</label>
                <input
                  type="url"
                  value={seed.website}
                  onChange={(e) => update("website", e.target.value)}
                  placeholder="https://acmecorp.com"
                  className={cn(
                    "w-full rounded-lg border bg-background px-3 py-2 text-sm",
                    "placeholder:text-muted-foreground/50",
                    "focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500",
                  )}
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium">
                  Social profiles
                </label>
                <input
                  type="text"
                  value={seed.socials}
                  onChange={(e) => update("socials", e.target.value)}
                  placeholder="@acmecorp on Instagram, LinkedIn page URL..."
                  className={cn(
                    "w-full rounded-lg border bg-background px-3 py-2 text-sm",
                    "placeholder:text-muted-foreground/50",
                    "focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500",
                  )}
                />
              </div>
            </div>
          </div>

          {/* Optional fields */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-sm font-medium">
                City / Region
              </label>
              <input
                type="text"
                value={seed.city}
                onChange={(e) => update("city", e.target.value)}
                placeholder="San Francisco, CA"
                className={cn(
                  "w-full rounded-lg border bg-background px-3 py-2 text-sm",
                  "placeholder:text-muted-foreground/50",
                  "focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500",
                )}
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">Industry</label>
              <input
                type="text"
                value={seed.industry}
                onChange={(e) => update("industry", e.target.value)}
                placeholder="Digital Marketing"
                className={cn(
                  "w-full rounded-lg border bg-background px-3 py-2 text-sm",
                  "placeholder:text-muted-foreground/50",
                  "focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500",
                )}
              />
            </div>
          </div>
        </div>
      </div>

      <div className="flex items-center justify-between border-t px-6 py-4">
        <span className="text-xs text-muted-foreground">
          {!canSubmit && !hasWebOrSocial && seed.company_name.trim() && seed.phone.trim()
            ? "Add a website or social profile so we can find your business"
            : "We'll search the web to research and verify your business"}
        </span>
        <button
          onClick={onSubmit}
          disabled={!canSubmit}
          className={cn(
            "flex items-center gap-2 rounded-lg px-5 py-2 text-sm font-medium text-white",
            "bg-amber-600 hover:bg-amber-700 disabled:opacity-40",
          )}
        >
          Start Research
          <ArrowRight className="h-4 w-4" />
        </button>
      </div>
    </>
  );
}

// ── Chat View ──

function ChatView({
  employeeName,
  messages,
  loading,
  profileDone,
  authError,
  onReconnect,
  input,
  onInputChange,
  onSend,
  onKeyDown,
  onDone,
  chatEndRef,
  inputRef,
}: {
  employeeName: string;
  messages: OnboardingMessage[];
  loading: boolean;
  profileDone: boolean;
  authError: string | null;
  onReconnect: () => void;
  input: string;
  onInputChange: (v: string) => void;
  onSend: () => void;
  onKeyDown: (e: React.KeyboardEvent) => void;
  onDone: () => void;
  chatEndRef: React.RefObject<HTMLDivElement | null>;
  inputRef: React.RefObject<HTMLTextAreaElement | null>;
}) {
  return (
    <>
      <div className="flex-1 overflow-y-auto px-6 py-4">
        <div className="space-y-4">
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
                  "max-w-[85%] rounded-xl px-4 py-2.5 text-sm leading-relaxed",
                  msg.role === "user" ? "bg-amber-600 text-white" : "bg-muted",
                )}
              >
                {msg.role === "assistant" ? (
                  <div className="space-y-2">
                    <span className="text-xs font-semibold text-amber-600 dark:text-amber-400">
                      {employeeName}
                    </span>
                    <MarkdownMessage content={msg.content} />
                  </div>
                ) : (
                  <MarkdownMessage content={msg.content} />
                )}
              </div>
            </div>
          ))}

          {loading && (
            <div className="flex justify-start">
              <div className="flex items-center gap-2 rounded-xl bg-muted px-4 py-3 text-sm">
                <span className="text-xs font-semibold text-amber-600 dark:text-amber-400">
                  {employeeName}
                </span>
                <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                <span className="text-muted-foreground">Researching...</span>
              </div>
            </div>
          )}

          <div ref={chatEndRef} />
        </div>
      </div>

      {/* Auth error banner */}
      {authError && (
        <div className="mx-4 mb-2 flex items-center gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 dark:border-red-900 dark:bg-red-950/30">
          <AlertTriangle className="h-5 w-5 shrink-0 text-red-600 dark:text-red-400" />
          <div className="flex-1">
            <p className="text-sm font-medium text-red-800 dark:text-red-300">
              {authError === "token_expired"
                ? "Your Claude connection has expired."
                : "Claude CLI isn't connected."}
            </p>
            <p className="text-xs text-red-600 dark:text-red-400">
              Reconnect to continue building your profile.
            </p>
          </div>
          <button
            onClick={onReconnect}
            className="flex items-center gap-1.5 rounded-lg bg-red-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-700"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Reconnect
          </button>
        </div>
      )}

      <div className="border-t px-4 py-3">
        {profileDone ? (
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-green-600 dark:text-green-400">
              Profile built successfully!
            </span>
            <button
              onClick={onDone}
              className="rounded-lg bg-green-600 px-5 py-2 text-sm font-medium text-white hover:bg-green-700"
            >
              Done
            </button>
          </div>
        ) : (
          <div className="flex items-end gap-2">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => onInputChange(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder={`Reply to ${employeeName}...`}
              rows={1}
              disabled={loading}
              className={cn(
                "flex-1 resize-none rounded-lg border bg-background px-3 py-2 text-sm",
                "placeholder:text-muted-foreground/50",
                "focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500",
                "disabled:opacity-50",
              )}
              style={{ minHeight: "38px", maxHeight: "100px" }}
              onInput={(e) => {
                const el = e.target as HTMLTextAreaElement;
                el.style.height = "auto";
                el.style.height = Math.min(el.scrollHeight, 100) + "px";
              }}
            />
            <button
              onClick={onSend}
              disabled={loading || !input.trim()}
              className={cn(
                "flex h-[38px] w-[38px] items-center justify-center rounded-lg",
                "bg-amber-600 text-white hover:bg-amber-700",
                "disabled:opacity-40",
              )}
            >
              <Send className="h-4 w-4" />
            </button>
          </div>
        )}
      </div>
    </>
  );
}
