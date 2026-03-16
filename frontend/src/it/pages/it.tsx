import { useState, useRef, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ChevronDown,
  Cpu,
  Zap,
  Globe,
  CheckCircle2,
  Loader2,
  Unplug,
  Play,
  Square,
  AlertCircle,
  X,
  MessageSquare,
  Send,
  Monitor,
  Wrench,
  Github,
  Cloud,
  XCircle,
  Terminal,
} from "lucide-react";
import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { PageHeader } from "@/shared/components/page-header";
import { MarkdownMessage } from "@/shared/components/ui/markdown-message";
import { useAppStore } from "@/shared/stores/app-store";
import { useSetupStore } from "@/shared/stores/setup-store";
import { getProviderStatus, startClaudeLogin, getCliStatus, listDepartments, listEmployees } from "@/shared/api/organization";
import { getCliConnectionStatus, disconnectCli } from "@/shared/api/platforms";
import { sendEmployeeChat, type ChatMessage } from "@/shared/api/chat";
import {
  getNgrokStatus,
  connectNgrok,
  disconnectNgrok,
  startNgrokTunnel,
  stopNgrokTunnel,
} from "@/shared/api/ngrok";
import { ClaudeTerminalModal } from "@/shared/components/terminal/claude-terminal-modal";
import { cn } from "@/shared/lib/utils";

// ── Collapsible Section ──

function CollapsibleSection({
  icon,
  title,
  subtitle,
  open,
  onToggle,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  subtitle?: string;
  open: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-border bg-card">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center justify-between px-5 py-4 text-left transition-colors hover:bg-muted/50"
      >
        <span className="flex items-center gap-2.5">
          <span className="text-primary">{icon}</span>
          <span className="font-semibold">{title}</span>
          {subtitle && (
            <span className="text-xs text-muted-foreground">{subtitle}</span>
          )}
        </span>
        <ChevronDown
          size={16}
          className={cn(
            "text-muted-foreground transition-transform duration-200",
            open && "rotate-180",
          )}
        />
      </button>
      {open && <div className="border-t border-border px-5 py-5">{children}</div>}
    </div>
  );
}

// ── Chat Section ──

function ChatSection({
  businessId,
  employeeId,
  employeeName,
}: {
  businessId: string;
  employeeId: string;
  employeeName: string;
}) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  const mutation = useMutation({
    mutationFn: (userMessage: string) =>
      sendEmployeeChat({
        business_id: businessId,
        employee_id: employeeId,
        messages,
        user_message: userMessage,
      }),
    onSuccess: (data, userMessage) => {
      setMessages((prev) => [
        ...prev,
        { role: "user", content: userMessage },
        { role: "assistant", content: data.content },
      ]);
    },
  });

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, mutation.isPending]);

  const handleSend = () => {
    const trimmed = input.trim();
    if (!trimmed || mutation.isPending) return;
    setInput("");
    mutation.mutate(trimmed);
  };

  return (
    <div className="flex flex-col">
      <div ref={scrollRef} className="max-h-96 min-h-[200px] overflow-y-auto space-y-3 mb-4">
        {messages.length === 0 && !mutation.isPending && (
          <div className="flex flex-col items-center justify-center py-12 text-center">
            <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-primary/10">
              <MessageSquare size={20} className="text-primary" />
            </div>
            <p className="text-sm font-medium">Chat with {employeeName}</p>
            <p className="mt-1 text-xs text-muted-foreground max-w-sm">
              Ask about infrastructure, deploy websites, manage GitHub repos, fix employee prompts, or perform system administration tasks.
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
              <span className="text-xs text-muted-foreground">Thinking...</span>
            </div>
          </div>
        )}
      </div>

      {mutation.isError && (
        <p className="mb-2 text-xs text-destructive">
          {mutation.error instanceof Error ? mutation.error.message : "Failed to send message"}
        </p>
      )}

      <div className="flex gap-2">
        <Input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleSend()}
          placeholder={`Ask ${employeeName}...`}
          className="text-sm"
          disabled={mutation.isPending}
        />
        <Button
          size="sm"
          onClick={handleSend}
          disabled={!input.trim() || mutation.isPending}
        >
          <Send className="h-3.5 w-3.5" />
        </Button>
      </div>
    </div>
  );
}

// ── Claude AI Section ──

function ClaudeSection({ businessId }: { businessId: string }) {
  const queryClient = useQueryClient();
  const { setClaudeConnected } = useSetupStore();
  const [showTerminal, setShowTerminal] = useState(false);
  const [connectLoading, setConnectLoading] = useState(false);

  const { data: providerStatus } = useQuery({
    queryKey: ["provider-status", businessId],
    queryFn: () => getProviderStatus(businessId),
    enabled: !!businessId,
    refetchInterval: 15_000,
  });

  const { data: cliStatus } = useQuery({
    queryKey: ["cli-status", businessId],
    queryFn: () => getCliConnectionStatus(businessId),
    enabled: !!businessId,
  });

  const isConnected = providerStatus?.ready ?? false;

  const handleConnect = async () => {
    setConnectLoading(true);
    try {
      const result = await startClaudeLogin(businessId);
      if (result.status === "already_authenticated") {
        setClaudeConnected(true);
        queryClient.invalidateQueries({ queryKey: ["provider-status"] });
        queryClient.invalidateQueries({ queryKey: ["cli-status"] });
      } else {
        setShowTerminal(true);
      }
    } catch {
      setShowTerminal(true);
    } finally {
      setConnectLoading(false);
    }
  };

  const disconnectMutation = useMutation({
    mutationFn: () => disconnectCli(businessId),
    onSuccess: () => {
      setClaudeConnected(false);
      queryClient.invalidateQueries({ queryKey: ["provider-status"] });
      queryClient.invalidateQueries({ queryKey: ["cli-status"] });
    },
  });

  const handleTerminalAuth = () => {
    setClaudeConnected(true);
    queryClient.invalidateQueries({ queryKey: ["provider-status"] });
    queryClient.invalidateQueries({ queryKey: ["cli-status"] });
  };

  if (isConnected) {
    return (
      <>
        <div className="flex items-center gap-3 rounded-lg border border-green-200 dark:border-green-900 bg-green-50/50 dark:bg-green-950/30 px-4 py-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-green-500/10">
            <CheckCircle2 className="h-4 w-4 text-green-600" />
          </div>
          <div className="flex-1">
            <p className="text-sm font-medium text-green-700 dark:text-green-400">Claude AI Connected</p>
            <p className="text-xs text-green-600/70 dark:text-green-500/70">
              {cliStatus?.version ? `v${cliStatus.version}` : "Active"}{" "}
              {cliStatus?.connected_at && `· Connected ${new Date(cliStatus.connected_at).toLocaleDateString()}`}
            </p>
          </div>
          <Button
            size="sm"
            variant="ghost"
            className="h-7 text-xs text-red-600 hover:text-red-700"
            onClick={() => disconnectMutation.mutate()}
            disabled={disconnectMutation.isPending}
          >
            <Unplug className="h-3 w-3 mr-1" /> Disconnect
          </Button>
        </div>

        <ClaudeTerminalModal
          isOpen={showTerminal}
          onClose={() => setShowTerminal(false)}
          businessId={businessId}
          onAuthenticated={handleTerminalAuth}
        />
      </>
    );
  }

  return (
    <>
      <div className="flex flex-col items-center justify-center rounded-lg border-2 border-dashed border-amber-300 dark:border-amber-800 bg-amber-50/50 dark:bg-amber-950/20 px-6 py-8">
        <Cpu className="h-10 w-10 mb-3 text-amber-500 opacity-60" />
        <p className="text-sm font-semibold text-amber-700 dark:text-amber-400">Connect AI to get started</p>
        <p className="text-xs text-amber-600/70 dark:text-amber-500/60 mt-1 text-center max-w-sm">
          Link your Claude account to power your AI workforce. This enables all department heads to handle tasks autonomously.
        </p>
        <Button
          size="sm"
          className="mt-4 bg-violet-600 hover:bg-violet-700 text-white"
          onClick={handleConnect}
          disabled={connectLoading}
        >
          {connectLoading ? (
            <Loader2 className="h-3 w-3 mr-1 animate-spin" />
          ) : (
            <Zap className="h-3 w-3 mr-1" />
          )}
          {connectLoading ? "Checking..." : "Connect Claude"}
        </Button>
      </div>

      <ClaudeTerminalModal
        isOpen={showTerminal}
        onClose={() => setShowTerminal(false)}
        businessId={businessId}
        onAuthenticated={handleTerminalAuth}
      />
    </>
  );
}

// ── Ngrok Section ──

function NgrokSection({ businessId }: { businessId: string }) {
  const queryClient = useQueryClient();
  const [showModal, setShowModal] = useState(false);
  const [authToken, setAuthToken] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { data: ngrokStatus, isLoading } = useQuery({
    queryKey: ["ngrok-status", businessId],
    queryFn: () => getNgrokStatus(businessId),
    enabled: !!businessId,
    refetchInterval: 10_000,
  });

  const connected = ngrokStatus?.connected ?? false;
  const tunnelActive = ngrokStatus?.tunnel_active ?? false;

  const connectMutation = useMutation({
    mutationFn: () => connectNgrok({ business_id: businessId, auth_token: authToken.trim() }),
    onSuccess: () => {
      setShowModal(false);
      setAuthToken("");
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["ngrok-status"] });
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? "Failed to connect ngrok.";
      setError(msg);
    },
  });

  const disconnectMutation = useMutation({
    mutationFn: () => disconnectNgrok(businessId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["ngrok-status"] }),
  });

  const startMutation = useMutation({
    mutationFn: () => startNgrokTunnel(businessId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["ngrok-status"] }),
  });

  const stopMutation = useMutation({
    mutationFn: () => stopNgrokTunnel(businessId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["ngrok-status"] }),
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-6 text-muted-foreground text-sm">
        <Loader2 className="h-4 w-4 animate-spin mr-2" /> Checking ngrok status...
      </div>
    );
  }

  if (!connected) {
    return (
      <>
        <div className="flex flex-col items-center justify-center rounded-lg border-2 border-dashed border-border bg-muted/30 px-6 py-8">
          <Globe className="h-10 w-10 mb-3 text-muted-foreground opacity-40" />
          <p className="text-sm font-medium text-muted-foreground">Ngrok not connected</p>
          <p className="text-xs text-muted-foreground/70 mt-1 text-center max-w-sm">
            Connect ngrok to expose your local server for Twilio webhooks and external integrations.
          </p>
          <Button
            size="sm"
            variant="outline"
            className="mt-4"
            onClick={() => { setError(null); setShowModal(true); }}
          >
            <Globe className="h-3 w-3 mr-1" /> Connect Ngrok
          </Button>
        </div>

        {showModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
            <div className="relative w-full max-w-md rounded-xl bg-background p-6 shadow-xl">
              <button className="absolute right-4 top-4 text-muted-foreground hover:text-foreground" onClick={() => setShowModal(false)}>
                <X className="h-4 w-4" />
              </button>
              <h2 className="mb-1 text-lg font-semibold">Connect Ngrok</h2>
              <p className="mb-5 text-sm text-muted-foreground">
                Enter your ngrok auth token from{" "}
                <a href="https://dashboard.ngrok.com/get-started/your-authtoken" target="_blank" rel="noreferrer" className="text-violet-600 underline">
                  ngrok dashboard
                </a>.
              </p>
              <div className="space-y-4">
                <div>
                  <label className="mb-1 block text-sm font-medium">Auth Token</label>
                  <input
                    type="password"
                    placeholder="2abc..."
                    value={authToken}
                    onChange={(e) => setAuthToken(e.target.value)}
                    className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm font-mono placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                  />
                </div>
                {error && (
                  <div className="flex items-start gap-2 rounded-md bg-red-50 p-3 text-sm text-red-700 dark:bg-red-900/20 dark:text-red-300">
                    <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                    {error}
                  </div>
                )}
                <div className="flex justify-end gap-2 pt-2">
                  <Button variant="outline" onClick={() => setShowModal(false)} disabled={connectMutation.isPending}>Cancel</Button>
                  <Button
                    onClick={() => connectMutation.mutate()}
                    disabled={!authToken.trim() || connectMutation.isPending}
                  >
                    {connectMutation.isPending ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <CheckCircle2 className="mr-1 h-4 w-4" />}
                    {connectMutation.isPending ? "Connecting..." : "Connect"}
                  </Button>
                </div>
              </div>
            </div>
          </div>
        )}
      </>
    );
  }

  return (
    <div className="space-y-4">
      <div className={cn(
        "flex items-center gap-3 rounded-lg border px-4 py-3",
        tunnelActive
          ? "border-green-200 dark:border-green-900 bg-green-50/50 dark:bg-green-950/30"
          : "border-border bg-muted/30"
      )}>
        <div className={cn(
          "flex h-8 w-8 items-center justify-center rounded-full",
          tunnelActive ? "bg-green-500/10" : "bg-muted"
        )}>
          <Globe className={cn("h-4 w-4", tunnelActive ? "text-green-600" : "text-muted-foreground")} />
        </div>
        <div className="flex-1">
          <p className={cn(
            "text-sm font-medium",
            tunnelActive ? "text-green-700 dark:text-green-400" : "text-foreground"
          )}>
            {tunnelActive ? "Tunnel Active" : "Ngrok Connected"}
          </p>
          <p className="text-xs text-muted-foreground">
            {tunnelActive && ngrokStatus?.tunnel_url
              ? ngrokStatus.tunnel_url
              : ngrokStatus?.auth_token_preview
                ? `Token: ${ngrokStatus.auth_token_preview}`
                : "Ready to start tunnel"}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {tunnelActive ? (
            <Button
              size="sm"
              variant="outline"
              className="h-7 text-xs"
              onClick={() => stopMutation.mutate()}
              disabled={stopMutation.isPending}
            >
              {stopMutation.isPending ? <Loader2 className="h-3 w-3 mr-1 animate-spin" /> : <Square className="h-3 w-3 mr-1" />}
              Stop
            </Button>
          ) : (
            <Button
              size="sm"
              className="h-7 text-xs"
              onClick={() => startMutation.mutate()}
              disabled={startMutation.isPending}
            >
              {startMutation.isPending ? <Loader2 className="h-3 w-3 mr-1 animate-spin" /> : <Play className="h-3 w-3 mr-1" />}
              Start Tunnel
            </Button>
          )}
          <Button
            size="sm"
            variant="ghost"
            className="h-7 text-xs text-red-600 hover:text-red-700"
            onClick={() => disconnectMutation.mutate()}
            disabled={disconnectMutation.isPending}
          >
            <Unplug className="h-3 w-3 mr-1" /> Disconnect
          </Button>
        </div>
      </div>
    </div>
  );
}

// ── CLI Tool Status (GitHub / Azure) ──

interface CliToolInfo {
  installed: boolean;
  authenticated: boolean;
  user?: string | null;
  details?: string | null;
  login_cmd: string;
}

function CliToolSection({
  name,
  icon,
  brandColor,
  description,
  tool,
}: {
  name: string;
  icon: React.ReactNode;
  brandColor: string;
  description: string;
  tool: CliToolInfo | undefined;
}) {
  if (!tool) {
    return (
      <div className="flex items-center gap-3 rounded-lg border border-border bg-muted/30 px-4 py-3">
        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-muted">
          {icon}
        </div>
        <div className="flex-1">
          <p className="text-sm font-medium text-muted-foreground">{name}</p>
          <p className="text-xs text-muted-foreground/70">Loading...</p>
        </div>
        <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!tool.installed) {
    return (
      <div className="flex items-center gap-3 rounded-lg border border-border bg-muted/30 px-4 py-3">
        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-muted">
          {icon}
        </div>
        <div className="flex-1">
          <p className="text-sm font-medium text-muted-foreground">{name}</p>
          <p className="text-xs text-muted-foreground/70">Not installed on server</p>
        </div>
        <XCircle size={14} className="shrink-0 text-muted-foreground" />
      </div>
    );
  }

  if (tool.authenticated) {
    return (
      <div className="flex items-center gap-3 rounded-lg border border-green-200 dark:border-green-900 bg-green-50/50 dark:bg-green-950/30 px-4 py-3">
        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-green-500/10">
          {icon}
        </div>
        <div className="flex-1">
          <p className="text-sm font-medium text-green-700 dark:text-green-400">{name} Connected</p>
          <p className="text-xs text-green-600/70 dark:text-green-500/70">
            {(() => {
              if (!tool.details) return "Authenticated";
              // Try parsing JSON (az account show returns JSON)
              try {
                const parsed = JSON.parse(tool.details);
                if (parsed.name) return parsed.name;
                if (parsed.user?.name) return parsed.user.name;
              } catch {
                // Not JSON — use first meaningful line (gh auth status)
              }
              const line = tool.details.split("\n").find((l: string) => l.trim() && !l.trim().startsWith("{") && !l.trim().startsWith("}"));
              return line?.trim().slice(0, 80) || "Authenticated";
            })()}
          </p>
        </div>
        <CheckCircle2 size={14} className="shrink-0 text-green-500" />
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center justify-center rounded-lg border-2 border-dashed border-border bg-muted/30 px-6 py-6">
      <div className={cn("mb-2", brandColor)}>{icon}</div>
      <p className="text-sm font-medium text-muted-foreground">{name} not authenticated</p>
      <p className="text-xs text-muted-foreground/70 mt-1 text-center max-w-sm">{description}</p>
      <div className="mt-3 flex items-center gap-1.5 rounded-md bg-muted px-3 py-1.5">
        <Terminal className="h-3 w-3 text-muted-foreground" />
        <code className="text-xs font-mono text-muted-foreground">{tool.login_cmd}</code>
      </div>
    </div>
  );
}

// ── Main IT Page ──

export default function ITPage() {
  const { activeBusiness } = useAppStore();
  const businessId = activeBusiness?.id ?? "";

  const [chatOpen, setChatOpen] = useState(true);
  const [toolsOpen, setToolsOpen] = useState(false);

  // CLI auth status (GitHub, Azure)
  const cliAuthQuery = useQuery({
    queryKey: ["cli-auth-status"],
    queryFn: () => getCliStatus(),
    enabled: !!businessId,
    refetchInterval: 30_000,
  });

  const cliTools = cliAuthQuery.data?.tools as Record<string, CliToolInfo> | undefined;

  // Find IT department + head employee
  const departmentsQuery = useQuery({
    queryKey: ["it-departments", businessId],
    queryFn: () => listDepartments(businessId!),
    enabled: !!businessId,
  });

  const itDept = departmentsQuery.data?.find((d) => d.name === "IT");

  const employeesQuery = useQuery({
    queryKey: ["it-employees", businessId, itDept?.id],
    queryFn: () => listEmployees({ business_id: businessId!, department_id: itDept!.id }),
    enabled: !!businessId && !!itDept?.id,
  });

  const itHead = employeesQuery.data?.find((e) => e.is_head);

  if (!businessId) {
    return (
      <div className="flex flex-col h-full items-center justify-center gap-2 text-muted-foreground">
        <Monitor className="h-8 w-8" />
        <p className="text-sm">No business selected</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6 p-6">
      <PageHeader
        title="IT"
        description={itHead ? `${itHead.name} — ${itHead.title}` : "Infrastructure and system administration"}
      />

      {/* Chat — main section, default open */}
      <CollapsibleSection
        icon={<MessageSquare size={18} />}
        title="Chat"
        subtitle={itHead?.name}
        open={chatOpen}
        onToggle={() => setChatOpen((v) => !v)}
      >
        {itHead ? (
          <ChatSection
            businessId={businessId}
            employeeId={itHead.id}
            employeeName={itHead.name}
          />
        ) : (
          <div className="flex flex-col items-center justify-center py-8 text-center text-muted-foreground">
            <Monitor size={32} className="mb-2 opacity-40" />
            <p className="text-sm">
              No IT director found. Create an IT department head to enable chat.
            </p>
          </div>
        )}
      </CollapsibleSection>

      {/* System Tools — collapsed by default */}
      <CollapsibleSection
        icon={<Wrench size={18} />}
        title="System Tools"
        subtitle="Connections & Infrastructure"
        open={toolsOpen}
        onToggle={() => setToolsOpen((v) => !v)}
      >
        <div className="space-y-6">
          <div>
            <p className="mb-3 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              AI Provider
            </p>
            <ClaudeSection businessId={businessId} />
          </div>
          <div>
            <p className="mb-3 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              Source Control
            </p>
            <CliToolSection
              name="GitHub"
              icon={<Github className="h-4 w-4" />}
              brandColor="text-gray-700 dark:text-gray-300"
              description="Authenticate with GitHub to create repos, deploy to GitHub Pages, and manage code."
              tool={cliTools?.gh}
            />
          </div>
          <div>
            <p className="mb-3 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              Cloud Hosting
            </p>
            <CliToolSection
              name="Azure"
              icon={<Cloud className="h-4 w-4" />}
              brandColor="text-blue-500"
              description="Authenticate with Azure to deploy production websites and manage cloud resources."
              tool={cliTools?.az}
            />
          </div>
          <div>
            <p className="mb-3 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              Tunnel Management
            </p>
            <NgrokSection businessId={businessId} />
          </div>
        </div>
      </CollapsibleSection>
    </div>
  );
}
