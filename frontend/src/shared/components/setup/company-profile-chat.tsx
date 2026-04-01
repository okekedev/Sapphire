/**
 * Inline Company Profile builder — same chat pattern as department tabs.
 * Shows seed fields initially, then switches to a chat with the Marketing head.
 * Supports regenerating an existing profile with confirmation.
 */
import { useState, useRef, useEffect, useCallback } from "react";
import { useMutation } from "@tanstack/react-query";
import {
  Loader2,
  Send,
  MessageSquare,
  RefreshCw,
  AlertTriangle,
} from "lucide-react";
import { MarkdownMessage } from "@/shared/components/ui/markdown-message";
import { cn } from "@/shared/lib/utils";
import {
  sendOnboardingMessage,
  type SeedInfo,
  type OnboardingMessage,
  type OnboardingResponse,
} from "@/shared/api/businesses";
import { ClaudeTerminalModal } from "@/shared/components/terminal/claude-terminal-modal";

interface CompanyProfileChatProps {
  businessId: string;
  hasExistingProfile: boolean;
  onProfileSaved?: () => void;
}

export function CompanyProfileChat({
  businessId,
  hasExistingProfile,
  onProfileSaved,
}: CompanyProfileChatProps) {
  // Seed form state
  const [seed, setSeed] = useState<SeedInfo>({
    company_name: "",
    phone: "",
    city: "",
    industry: "",
    website: "",
    socials: "",
  });
  const [seedSubmitted, setSeedSubmitted] = useState(hasExistingProfile);

  // Chat state
  const [messages, setMessages] = useState<OnboardingMessage[]>(
    hasExistingProfile
      ? [{ role: "assistant", content: "Your profile is built! Tell me what you'd like to update — I can refine any section, add new information, or rebuild the whole profile from scratch." }]
      : [],
  );
  const [input, setInput] = useState("");
  const [employeeName, setEmployeeName] = useState("Assistant");
  const [profileDone, setProfileDone] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);
  const [showTerminal, setShowTerminal] = useState(false);

  // Regenerate confirmation
  const [showRegenConfirm, setShowRegenConfirm] = useState(false);

  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const seedInfoRef = useRef<SeedInfo | null>(null);
  const lastMessageRef = useRef<{ msg: string; isFirst: boolean } | null>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages]);

  const showSeedForm = !seedSubmitted && !hasExistingProfile;

  const mutation = useMutation({
    mutationFn: async ({
      userMsg,
      isFirst,
    }: {
      userMsg: string;
      isFirst: boolean;
    }): Promise<OnboardingResponse> => {
      lastMessageRef.current = { msg: userMsg, isFirst };
      return sendOnboardingMessage(
        businessId,
        userMsg,
        isFirst ? [] : messages,
        isFirst ? seedInfoRef.current ?? undefined : undefined,
      );
    },
    onMutate: ({ userMsg }) => {
      // Show user message immediately
      setMessages((prev) => [...prev, { role: "user", content: userMsg }]);
    },
    onSuccess: (res) => {
      if (res.employee_name) setEmployeeName(res.employee_name);

      if (res.auth_error && res.auth_error_type) {
        setAuthError(res.auth_error_type);
        return;
      }

      // Strip ```markdown:profile fences so the profile renders as formatted markdown
      const cleaned = res.response
        .replace(/```markdown:profile\s*\n/g, "")
        .replace(/\n```\s*$/g, "")
        .replace(/\n```(\s*\n)/g, "$1");

      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: cleaned },
      ]);

      if (res.onboarding_complete) {
        setProfileDone(true);
        onProfileSaved?.();
      }
    },
    onError: () => {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "Sorry, I had trouble connecting. Please try again.",
        },
      ]);
    },
  });

  const handleReconnectSuccess = useCallback(() => {
    setShowTerminal(false);
    setAuthError(null);
    if (lastMessageRef.current) {
      const { msg, isFirst } = lastMessageRef.current;
      mutation.mutate({ userMsg: msg, isFirst });
    }
  }, [mutation]);

  const handleSeedSubmit = useCallback(() => {
    const hasName = seed.company_name.trim();
    const hasPhone = seed.phone.trim();
    const hasWebOrSocial = seed.website.trim() || seed.socials.trim();
    if (!hasName || !hasPhone || !hasWebOrSocial) return;

    seedInfoRef.current = seed;
    setSeedSubmitted(true);

    const parts = [`My company is ${seed.company_name.trim()}.`];
    if (seed.phone) parts.push(`Phone: ${seed.phone}.`);
    if (seed.city) parts.push(`Based in ${seed.city}.`);
    if (seed.industry) parts.push(`Industry: ${seed.industry}.`);
    if (seed.website) parts.push(`Website: ${seed.website}.`);
    if (seed.socials) parts.push(`Socials: ${seed.socials}.`);
    parts.push("Please research us and build our company profile.");

    mutation.mutate({ userMsg: parts.join(" "), isFirst: true });
  }, [seed, mutation]);

  const handleRegenerate = useCallback(() => {
    setShowRegenConfirm(true);
  }, []);

  const handleRegenConfirmed = useCallback(() => {
    setShowRegenConfirm(false);
    // Show the seed form for regeneration
    setSeedSubmitted(false);
    setMessages([]);
    setProfileDone(false);
  }, []);

  const handleSend = useCallback(() => {
    const trimmed = input.trim();
    if (!trimmed || mutation.isPending) return;
    setInput("");
    mutation.mutate({ userMsg: trimmed, isFirst: false });
  }, [input, mutation]);

  const update = (key: keyof SeedInfo, value: string) =>
    setSeed((s) => ({ ...s, [key]: value }));

  const hasWebOrSocial = seed.website.trim() || seed.socials.trim();
  const canSubmit =
    seed.company_name.trim() && seed.phone.trim() && hasWebOrSocial;

  return (
    <div className="flex flex-col">
      {/* Seed form — shown before first submit */}
      {(showSeedForm || showRegenConfirm) && (
        <div className="mb-4 space-y-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label className="mb-1 block text-xs font-medium text-muted-foreground">
                Business name *
              </label>
              <input
                type="text"
                value={seed.company_name}
                onChange={(e) => update("company_name", e.target.value)}
                placeholder="Acme Corp"
                className={cn(
                  "w-full rounded-md border bg-background px-3 py-2 text-sm",
                  "placeholder:text-muted-foreground/50",
                  "focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary",
                )}
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-muted-foreground">
                Phone *
              </label>
              <input
                type="tel"
                value={seed.phone}
                onChange={(e) => update("phone", e.target.value)}
                placeholder="(555) 123-4567"
                className={cn(
                  "w-full rounded-md border bg-background px-3 py-2 text-sm",
                  "placeholder:text-muted-foreground/50",
                  "focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary",
                )}
              />
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label className="mb-1 block text-xs font-medium text-muted-foreground">
                Website *
              </label>
              <input
                type="url"
                value={seed.website}
                onChange={(e) => update("website", e.target.value)}
                placeholder="https://acmecorp.com"
                className={cn(
                  "w-full rounded-md border bg-background px-3 py-2 text-sm",
                  "placeholder:text-muted-foreground/50",
                  "focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary",
                )}
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-muted-foreground">
                Social profiles
              </label>
              <input
                type="text"
                value={seed.socials}
                onChange={(e) => update("socials", e.target.value)}
                placeholder="@acmecorp on Instagram..."
                className={cn(
                  "w-full rounded-md border bg-background px-3 py-2 text-sm",
                  "placeholder:text-muted-foreground/50",
                  "focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary",
                )}
              />
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label className="mb-1 block text-xs font-medium text-muted-foreground">
                City / Region
              </label>
              <input
                type="text"
                value={seed.city}
                onChange={(e) => update("city", e.target.value)}
                placeholder="San Francisco, CA"
                className={cn(
                  "w-full rounded-md border bg-background px-3 py-2 text-sm",
                  "placeholder:text-muted-foreground/50",
                  "focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary",
                )}
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-muted-foreground">
                Industry
              </label>
              <input
                type="text"
                value={seed.industry}
                onChange={(e) => update("industry", e.target.value)}
                placeholder="Digital Marketing"
                className={cn(
                  "w-full rounded-md border bg-background px-3 py-2 text-sm",
                  "placeholder:text-muted-foreground/50",
                  "focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary",
                )}
              />
            </div>
          </div>

          <div className="flex items-center justify-between pt-1">
            <p className="text-xs text-muted-foreground">
              {!canSubmit && !hasWebOrSocial && seed.company_name.trim() && seed.phone.trim()
                ? "Add a website or social profile so we can find your business"
                : "We'll research your business online and build a profile"}
            </p>
            <button
              onClick={handleSeedSubmit}
              disabled={!canSubmit}
              className={cn(
                "rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground",
                "hover:bg-primary/90 disabled:opacity-40",
              )}
            >
              Start Research
            </button>
          </div>
        </div>
      )}

      {/* Regen confirmation */}
      {showRegenConfirm && !seedSubmitted && messages.length === 0 && (
        <div className="mb-2 flex items-center gap-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs dark:border-amber-800 dark:bg-amber-950/30">
          <AlertTriangle size={14} className="shrink-0 text-amber-600" />
          <span className="text-amber-800 dark:text-amber-300">
            This will replace your existing company profile. Fill in the details above and click Start Research.
          </span>
        </div>
      )}

      {/* Chat messages — shown after seed submitted */}
      {seedSubmitted && (
        <>
          <div
            ref={scrollRef}
            className="max-h-96 min-h-[200px] space-y-3 overflow-y-auto mb-4"
          >
            {messages.length === 0 && !mutation.isPending && (
              <div className="flex flex-col items-center justify-center py-12 text-center">
                <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-primary/10">
                  <MessageSquare size={20} className="text-primary" />
                </div>
                <p className="text-sm font-medium">Chat with {employeeName}</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Researching your business and building your company profile.
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
                    "max-w-[80%] rounded-lg px-4 py-2.5 text-sm leading-relaxed",
                    msg.role === "user"
                      ? "bg-primary text-primary-foreground"
                      : "bg-muted",
                  )}
                >
                  {msg.role === "assistant" && (
                    <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                      {employeeName}
                    </p>
                  )}
                  {msg.role === "assistant" ? (
                    <MarkdownMessage content={msg.content} />
                  ) : (
                    <p>{msg.content}</p>
                  )}
                </div>
              </div>
            ))}

            {mutation.isPending && (
              <div className="flex justify-start">
                <div className="flex items-center gap-2 rounded-lg bg-muted px-4 py-3">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  <span className="text-xs text-muted-foreground">
                    Researching...
                  </span>
                </div>
              </div>
            )}
          </div>

          {/* Auth error banner */}
          {authError && (
            <div className="mb-3 flex items-center gap-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 dark:border-red-900 dark:bg-red-950/30">
              <AlertTriangle size={14} className="shrink-0 text-red-600 dark:text-red-400" />
              <p className="flex-1 text-xs text-red-800 dark:text-red-300">
                {authError === "token_expired"
                  ? "Claude connection expired."
                  : "Claude CLI isn't connected."}
              </p>
              <button
                onClick={() => setShowTerminal(true)}
                className="flex items-center gap-1 rounded bg-red-600 px-2 py-1 text-[10px] font-medium text-white hover:bg-red-700"
              >
                <RefreshCw size={10} />
                Reconnect
              </button>
            </div>
          )}

          {/* Profile complete banner */}
          {profileDone && (
            <div className="mb-3 rounded-md border border-green-200 bg-green-50 px-3 py-2 text-xs font-medium text-green-700 dark:border-green-900 dark:bg-green-950/30 dark:text-green-400">
              Profile built successfully! You can continue chatting or close this section.
            </div>
          )}

          {/* Chat input */}
          <div className="flex gap-2">
            <input
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) =>
                e.key === "Enter" && !e.shiftKey && handleSend()
              }
              placeholder={`Reply to ${employeeName}...`}
              className={cn(
                "flex-1 rounded-md border bg-background px-3 py-2 text-sm",
                "placeholder:text-muted-foreground/50",
                "focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary",
                "disabled:opacity-50",
              )}
              disabled={mutation.isPending}
            />
            <button
              onClick={handleSend}
              disabled={!input.trim() || mutation.isPending}
              className={cn(
                "flex h-9 w-9 items-center justify-center rounded-md",
                "bg-primary text-primary-foreground hover:bg-primary/90",
                "disabled:opacity-40",
              )}
            >
              <Send size={14} />
            </button>
          </div>
        </>
      )}

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
