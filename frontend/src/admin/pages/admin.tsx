import { useState, useRef, useEffect, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Phone,
  Hash,
  MessageSquare,
  ChevronDown,
  Send,
  Loader2,
  PhoneForwarded,
  Mic,
  Volume2,
  GitBranch,
  Pencil,
  Check,
  X,
  Info,
  Plus,
  Plug,
  Trash2,
  Power,
  PhoneIncoming,
  Clock,
  Download,
  AlertTriangle,
  ShieldCheck,
  ShieldAlert,
} from "lucide-react";
import { cn } from "@/shared/lib/utils";
import { MarkdownMessage } from "@/shared/components/ui/markdown-message";
import { useAppStore } from "@/shared/stores/app-store";
// APIs
import { listEmployees, listDepartments } from "@/shared/api/organization";
import { sendEmployeeChat, type ChatMessage } from "@/shared/api/chat";
import {
  getTwilioStatus,
  connectTwilio,
  disconnectTwilio,
  listTwilioNumbers,
  getA2PStatus,
} from "@/admin/api/twilio";
import {
  getPhoneSettings,
  updatePhoneSettings,
  type PhoneSettingsRead,
  type PhoneSettingsUpdate,
  type DepartmentRoutingRule,
} from "@/marketing/api/tracking-routing";
import {
  getPhoneLines,
} from "@/marketing/api/contacts";
import {
  listCalls,
  verifyPhoneLine,
  type CallLogItem,
} from "@/marketing/api/tracking-routing";
import {
  registerWhatsAppSender,
  verifyWhatsAppSender,
  refreshWhatsAppStatus,
  sendWhatsAppTest,
} from "@/admin/api/whatsapp";

// ── Voice Options ──

const VOICE_OPTIONS = [
  { value: "Polly.Joanna-Neural", label: "Joanna — Female" },
  { value: "Polly.Matthew-Neural", label: "Matthew — Male" },
  { value: "Google.en-US-Chirp3-HD-Aoede", label: "Aoede — Female" },
  { value: "Google.en-US-Chirp3-HD-Leda", label: "Leda — Female" },
  { value: "Google.en-US-Chirp3-HD-Charon", label: "Charon — Male" },
  { value: "Google.en-US-Chirp3-HD-Puck", label: "Puck — Male" },
];

function VoiceSelector({
  value,
  onSave,
}: {
  value: string;
  onSave: (val: string) => void;
}) {
  return (
    <div>
      <p className="text-[11px] font-medium text-muted-foreground mb-0.5">Voice</p>
      <select
        value={value}
        onChange={(e) => onSave(e.target.value)}
        className="w-full rounded border border-border bg-background px-2.5 py-1.5 text-sm outline-none focus:border-primary transition-colors cursor-pointer"
      >
        {VOICE_OPTIONS.map((opt) => (
          <option key={opt.value} value={opt.value}>{opt.label}</option>
        ))}
      </select>
      <p className="text-[10px] text-muted-foreground mt-1">Call the mainline to test your voice selection.</p>
    </div>
  );
}

// ── Main Component ──

export default function AdminPage() {
  const business = useAppStore((s) => s.activeBusiness);
  const bizId = business?.id ?? "";

  const [mainlineOpen, setMainlineOpen] = useState(false);
  const [deptLinesOpen, setDeptLinesOpen] = useState(false);
  const [trackingNumbersOpen, setTrackingNumbersOpen] = useState(false);
  const [ivrOpen, setIvrOpen] = useState(false);
  const [callFlowOpen, setCallFlowOpen] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const [callLogOpen, setCallLogOpen] = useState(false);

  // Phone number action state
  const [editingDeptId, setEditingDeptId] = useState<string | null>(null);
  const [deptManualInput, setDeptManualInput] = useState(false);
  const [deptNumberDraft, setDeptNumberDraft] = useState("");

  const [confirmDisconnectDeptId, setConfirmDisconnectDeptId] = useState<string | null>(null);
  const [showSmsInfo, setShowSmsInfo] = useState(false);
  const [mainlineAction, setMainlineAction] = useState<"idle" | "manual">("idle");
  const [mainlineDraft, setMainlineDraft] = useState("");
  const [confirmRemoveTrackingId, setConfirmRemoveTrackingId] = useState<string | null>(null);
  const [verifyingLineId, setVerifyingLineId] = useState<string | null>(null);
  const [pendingChatMessage, setPendingChatMessage] = useState<string | null>(null);

  // Twilio connection
  const [twilioOpen, setTwilioOpen] = useState(false);
  const [showTwilioForm, setShowTwilioForm] = useState(false);
  const [twilioSid, setTwilioSid] = useState("");
  const [twilioToken, setTwilioToken] = useState("");
  const [twilioPhone, setTwilioPhone] = useState("");
  const [twilioError, setTwilioError] = useState<string | null>(null);

  const queryClient = useQueryClient();

  // Get admin department + head employee
  const { data: departments } = useQuery({
    queryKey: ["departments", bizId],
    queryFn: () => listDepartments(bizId),
    enabled: !!bizId,
  });

  const adminDept = departments?.find(
    (d) => d.name.toLowerCase() === "administration" || d.name.toLowerCase() === "admin",
  );

  const { data: allEmployees } = useQuery({
    queryKey: ["employees", bizId],
    queryFn: () => listEmployees({ business_id: bizId }),
    enabled: !!bizId,
  });

  const adminHead = allEmployees?.find(
    (e) => e.department_id === adminDept?.id && e.is_head,
  );

  // Twilio connection status
  const { data: twilioStatus } = useQuery({
    queryKey: ["twilio-status", bizId],
    queryFn: () => getTwilioStatus(bizId),
    enabled: !!bizId,
  });

  // Twilio numbers
  const { data: twilioNumbers } = useQuery({
    queryKey: ["twilio-numbers", bizId],
    queryFn: () => listTwilioNumbers(bizId),
    enabled: !!bizId && twilioStatus?.connected === true,
  });

  // Phone settings
  const { data: phoneSettings } = useQuery({
    queryKey: ["phone-settings", bizId],
    queryFn: () => getPhoneSettings(bizId),
    enabled: !!bizId,
    staleTime: 30_000, // avoid redundant refetches for 30s
  });

  // Tracking numbers (mainline + campaigns)
  const { data: trackingNumbers } = useQuery({
    queryKey: ["phone-lines", bizId],
    queryFn: () => getPhoneLines(bizId),
    enabled: !!bizId,
  });

  const { data: callLogData } = useQuery({
    queryKey: ["admin-call-log", bizId],
    queryFn: () => listCalls(bizId, { limit: 50, sort_by: "date", sort_order: "desc" }),
    enabled: !!bizId,
    refetchInterval: 30_000, // Auto-refresh every 30s
  });

  const { data: a2pStatus } = useQuery({
    queryKey: ["a2p-status", bizId],
    queryFn: () => getA2PStatus(bizId),
    enabled: !!bizId,
    refetchInterval: 60_000, // Check every 60s
  });

  // Verify phone line handler
  const handleVerifyLine = async (lineId: string) => {
    if (!bizId || verifyingLineId) return;
    setVerifyingLineId(lineId);
    try {
      await verifyPhoneLine(bizId, lineId);
      queryClient.invalidateQueries({ queryKey: ["phone-lines", bizId] });
    } catch (e: any) {
      console.error("[VERIFY]", e?.response?.data?.detail || e);
    } finally {
      setVerifyingLineId(null);
    }
  };

  const isConnected = twilioStatus?.connected ?? false;
  const mainlineNumber = trackingNumbers?.find((t) => t.line_type === "mainline");
  const campaignNumbers = trackingNumbers?.filter((t) => t.line_type !== "mainline" && t.active) ?? [];
  const deptConfig = (phoneSettings?.departments_config ?? []).filter(
    (d) => d.name !== "IT",
  );

  // Mutation: save departments_config
  const deptConfigMutation = useMutation({
    mutationFn: (newConfig: DepartmentRoutingRule[]) =>
      updatePhoneSettings(bizId, { departments_config: newConfig }),
    onSuccess: (data) => {
      queryClient.setQueryData<PhoneSettingsRead>(["phone-settings", bizId], data);
    },
  });

  const toggleDept = (deptId: string | null) => {
    const updated = deptConfig.map((d) => {
      if (d.department_id !== deptId) return d;
      // Can't enable without a forward number
      const wantsEnabled = !d.enabled;
      if (wantsEnabled && !d.forward_number) return d;
      return { ...d, enabled: wantsEnabled };
    });
    deptConfigMutation.mutate(updated);
  };

  const saveDeptForwardNumber = (deptId: string | null, number: string) => {
    const updated = deptConfig.map((d) =>
      d.department_id === deptId ? { ...d, forward_number: number || null } : d,
    );
    deptConfigMutation.mutate(updated);
    setEditingDeptId(null);
  };

  const toggleDeptSms = (deptId: string | null) => {
    const updated = deptConfig.map((d) =>
      d.department_id === deptId ? { ...d, sms_enabled: !d.sms_enabled } : d,
    );
    deptConfigMutation.mutate(updated);
  };

  const toggleDeptWhatsApp = (deptId: string | null) => {
    const updated = deptConfig.map((d) =>
      d.department_id === deptId ? { ...d, whatsapp_enabled: !d.whatsapp_enabled } : d,
    );
    deptConfigMutation.mutate(updated);
  };


  // General phone settings save — optimistic updates for instant UI
  const settingsMutation = useMutation({
    mutationFn: (payload: PhoneSettingsUpdate) =>
      updatePhoneSettings(bizId, payload),
    onMutate: async (payload) => {
      // Cancel in-flight refetches so they don't overwrite our optimistic update
      await queryClient.cancelQueries({ queryKey: ["phone-settings", bizId] });
      const previous = queryClient.getQueryData<PhoneSettingsRead>(["phone-settings", bizId]);
      // Optimistically merge the patch into the cache
      if (previous) {
        queryClient.setQueryData<PhoneSettingsRead>(["phone-settings", bizId], {
          ...previous,
          ...Object.fromEntries(Object.entries(payload).filter(([, v]) => v !== undefined)),
        } as PhoneSettingsRead);
      }
      return { previous };
    },
    onSuccess: (data) => {
      // Use server response directly — no extra refetch needed
      queryClient.setQueryData<PhoneSettingsRead>(["phone-settings", bizId], data);
    },
    onError: (_err, _payload, context) => {
      // Roll back to previous state on failure
      if (context?.previous) {
        queryClient.setQueryData(["phone-settings", bizId], context.previous);
      }
    },
  });

  const saveSettings = useCallback(
    (patch: PhoneSettingsUpdate) => settingsMutation.mutate(patch),
    [settingsMutation],
  );

  // Twilio connect/disconnect mutations
  const twilioConnectMutation = useMutation({
    mutationFn: () =>
      connectTwilio({
        business_id: bizId,
        account_sid: twilioSid.trim(),
        auth_token: twilioToken.trim(),
        phone_number: twilioPhone.trim() || undefined,
      }),
    onSuccess: () => {
      setShowTwilioForm(false);
      setTwilioSid("");
      setTwilioToken("");
      setTwilioPhone("");
      setTwilioError(null);
      queryClient.invalidateQueries({ queryKey: ["twilio-status"] });
      queryClient.invalidateQueries({ queryKey: ["twilio-numbers"] });
    },
    onError: (err: any) => {
      const msg = err?.response?.data?.detail ?? "Failed to connect Twilio account.";
      setTwilioError(msg);
    },
  });

  const twilioDisconnectMutation = useMutation({
    mutationFn: () => disconnectTwilio(bizId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["twilio-status"] });
      queryClient.invalidateQueries({ queryKey: ["twilio-numbers"] });
    },
  });

  const openChatWithMessage = (message: string) => {
    setChatOpen(true);
    setPendingChatMessage(message);
  };

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div>
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold">Admin</h1>
          <div className="relative group">
            <button
              type="button"
              className="flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs text-muted-foreground hover:text-foreground hover:bg-muted border border-transparent hover:border-border transition-colors"
            >
              <Info size={13} />
              <span>How to use</span>
            </button>
            <div className="absolute right-0 top-full mt-2 z-50 w-80 rounded-lg border border-border bg-popover p-4 shadow-lg opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all duration-150">
              <p className="text-xs font-semibold mb-2">IVR Phone System</p>
              <div className="space-y-1.5 text-[11px] leading-relaxed text-muted-foreground">
                <p><span className="font-medium text-foreground">Chat</span> — Talk to your admin AI to provision numbers, toggle settings, assign departments, or manage anything on this page conversationally.</p>
                <p><span className="font-medium text-foreground">Mainline</span> — Your primary business number. All inbound calls land here.</p>
                <p><span className="font-medium text-foreground">Departments</span> — AI transcribes and routes calls by intent. Each department can forward to its own number or stay on the mainline.</p>
                <p><span className="font-medium text-foreground">Tracking</span> — Assign unique numbers to campaigns to measure which ones drive calls.</p>
                <p><span className="font-medium text-foreground">IVR</span> — Configure greeting, voice, hold message, and recording preferences.</p>
              </div>
              <div className="mt-3 pt-2.5 border-t border-border">
                <p className="text-[10px] leading-relaxed text-amber-600 dark:text-amber-400">
                  <span className="font-semibold">Note:</span> If call recording is disabled, all calls default to Sales and are tracked by number only — not by department.
                </p>
              </div>
            </div>
          </div>
        </div>
        <p className="mt-1 text-sm text-muted-foreground">
          Phone system, IVR routing, and business configuration
        </p>
      </div>

      {/* ── Twilio Connection ── */}
      <CollapsibleSection
        icon={<Plug size={18} />}
        title="Twilio"
        subtitle={isConnected ? twilioStatus?.account_name || "Connected" : "Not connected"}
        open={twilioOpen}
        onToggle={() => setTwilioOpen((v) => !v)}
      >
        <div className="px-5 pb-4 space-y-3">
          {isConnected ? (
            <div className="rounded-md border border-emerald-200 dark:border-emerald-800 bg-emerald-50/50 dark:bg-emerald-900/10 px-3 py-2">
              <div className="flex items-center justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-medium text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400">Connected</span>
                    {twilioStatus?.account_name && (
                      <span className="text-xs text-muted-foreground">{twilioStatus.account_name}</span>
                    )}
                  </div>
                  {twilioStatus?.phone_number && (
                    <p className="text-sm font-mono mt-1">{twilioStatus.phone_number}</p>
                  )}
                </div>
                <div className="flex items-center gap-1.5">
                  <button
                    type="button"
                    onClick={() => { setTwilioError(null); setShowTwilioForm(true); }}
                    className="rounded border border-border px-2 py-0.5 text-[10px] font-medium text-muted-foreground hover:bg-muted transition-colors"
                  >
                    Reconnect
                  </button>
                  <button
                    type="button"
                    onClick={() => twilioDisconnectMutation.mutate()}
                    disabled={twilioDisconnectMutation.isPending}
                    className="rounded border border-red-200 dark:border-red-800 px-2 py-0.5 text-[10px] font-medium text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
                  >
                    {twilioDisconnectMutation.isPending ? "…" : "Disconnect"}
                  </button>
                </div>
              </div>
            </div>
          ) : (
            <div className="rounded-md border border-border px-3 py-2">
              <div className="flex items-center justify-between">
                <p className="text-sm text-muted-foreground">No Twilio account connected</p>
                <button
                  type="button"
                  onClick={() => { setTwilioError(null); setShowTwilioForm(true); }}
                  className="rounded border border-primary/30 bg-primary/5 px-2 py-0.5 text-[10px] font-medium text-primary hover:bg-primary/10 transition-colors"
                >
                  Connect Twilio
                </button>
              </div>
            </div>
          )}

          {/* Connect form */}
          {showTwilioForm && (
            <div className="rounded-md border border-border px-3 py-3 space-y-2.5">
              <p className="text-xs font-medium">Twilio Credentials</p>
              <p className="text-[10px] text-muted-foreground -mt-1">
                Find these in the <a href="https://console.twilio.com" target="_blank" rel="noreferrer" className="text-primary hover:underline">Twilio Console</a>.
              </p>
              <div className="space-y-2">
                <input
                  type="text"
                  value={twilioSid}
                  onChange={(e) => setTwilioSid(e.target.value)}
                  placeholder="Account SID"
                  className="w-full rounded border border-border bg-background px-2.5 py-1.5 text-sm outline-none focus:border-primary transition-colors font-mono"
                />
                <input
                  type="password"
                  value={twilioToken}
                  onChange={(e) => setTwilioToken(e.target.value)}
                  placeholder="Auth Token"
                  className="w-full rounded border border-border bg-background px-2.5 py-1.5 text-sm outline-none focus:border-primary transition-colors font-mono"
                />
                <input
                  type="tel"
                  value={twilioPhone}
                  onChange={(e) => setTwilioPhone(e.target.value)}
                  placeholder="Phone Number (optional)"
                  className="w-full rounded border border-border bg-background px-2.5 py-1.5 text-sm outline-none focus:border-primary transition-colors font-mono"
                />
              </div>
              {twilioError && (
                <p className="text-xs text-red-500">{twilioError}</p>
              )}
              <div className="flex items-center gap-1.5 pt-1">
                <button
                  type="button"
                  onClick={() => twilioConnectMutation.mutate()}
                  disabled={!twilioSid.trim() || !twilioToken.trim() || twilioConnectMutation.isPending}
                  className="rounded bg-primary px-3 py-1 text-xs font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50"
                >
                  {twilioConnectMutation.isPending ? "Connecting…" : "Connect"}
                </button>
                <button
                  type="button"
                  onClick={() => setShowTwilioForm(false)}
                  className="rounded border border-border px-3 py-1 text-xs text-muted-foreground hover:bg-muted transition-colors"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      </CollapsibleSection>

      {/* ── Chat ── */}
      {adminHead && (
        <CollapsibleSection
          icon={<MessageSquare size={18} />}
          title={`Chat — ${adminHead.name}`}
          subtitle={adminHead.title}
          open={chatOpen}
          onToggle={() => setChatOpen((v) => !v)}
        >
          <div className="px-5 pb-4">
            <ChatSection
              businessId={bizId}
              employeeId={adminHead.id}
              employeeName={adminHead.name}
              pendingMessage={pendingChatMessage}
              onPendingConsumed={() => setPendingChatMessage(null)}
            />
          </div>
        </CollapsibleSection>
      )}

      {/* ── Call Log ── */}
      <CollapsibleSection
        icon={<PhoneIncoming size={18} />}
        title="Call Log"
        subtitle={callLogData?.total ? `${callLogData.total} call${callLogData.total !== 1 ? "s" : ""}` : "No calls yet"}
        open={callLogOpen}
        onToggle={() => setCallLogOpen((v) => !v)}
      >
        <div className="px-5 pb-4">
          {/* Export CSV button */}
          {callLogData?.calls?.length ? (
            <div className="flex justify-end mb-3">
              <button
                onClick={() => {
                  const rows = callLogData.calls.map((c) => ({
                    "Call ID": c.id,
                    "Phone Number": c.caller_phone || "",
                    "Name": c.caller_name || "Unknown",
                    "Reason": c.summary || c.call_category || "",
                    "Department": c.routed_to || "Unrouted",
                    "Duration (s)": c.duration_s ?? "",
                    "Date": new Date(c.created_at).toLocaleString(),
                  }));
                  const headers = Object.keys(rows[0]);
                  const csv = [
                    headers.join(","),
                    ...rows.map((r) =>
                      headers.map((h) => `"${String((r as Record<string, unknown>)[h]).replace(/"/g, '""')}"`).join(",")
                    ),
                  ].join("\n");
                  const blob = new Blob([csv], { type: "text/csv" });
                  const url = URL.createObjectURL(blob);
                  const a = document.createElement("a");
                  a.href = url;
                  a.download = `call-log-${new Date().toISOString().slice(0, 10)}.csv`;
                  a.click();
                  URL.revokeObjectURL(url);
                }}
                className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-xs font-medium text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
              >
                <Download size={13} />
                Export CSV
              </button>
            </div>
          ) : null}
          {!callLogData?.calls?.length ? (
            <div className="text-center py-8 text-sm text-muted-foreground">
              <PhoneIncoming size={32} className="mx-auto mb-2 opacity-40" />
              <p>No inbound calls yet.</p>
              <p className="text-xs mt-1">Calls will appear here as they come in through your tracking numbers.</p>
            </div>
          ) : (
            <div className="overflow-x-auto rounded border border-border">
              <table className="min-w-full text-sm">
                <thead>
                  <tr className="bg-muted/50 text-left text-xs font-medium text-muted-foreground">
                    <th className="px-3 py-2">Phone Number</th>
                    <th className="px-3 py-2">Name</th>
                    <th className="px-3 py-2">Reason</th>
                    <th className="px-3 py-2">Department</th>
                    <th className="px-3 py-2">Duration</th>
                    <th className="px-3 py-2">Time</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {callLogData.calls.map((call) => (
                    <tr key={call.id} className="hover:bg-muted/30 transition-colors">
                      <td className="px-3 py-2 font-mono text-xs whitespace-nowrap">
                        {call.caller_phone
                          ? call.caller_phone.replace(/^\+1(\d{3})(\d{3})(\d{4})$/, "($1) $2-$3")
                          : "—"}
                      </td>
                      <td className="px-3 py-2 whitespace-nowrap">
                        {call.caller_name || <span className="text-muted-foreground">Unknown</span>}
                      </td>
                      <td className="px-3 py-2 max-w-[200px] truncate text-muted-foreground">
                        {call.summary || call.call_category || "—"}
                      </td>
                      <td className="px-3 py-2 whitespace-nowrap">
                        {call.routed_to ? (
                          <span className="inline-flex items-center gap-1 rounded-full bg-blue-50 dark:bg-blue-950 px-2 py-0.5 text-xs font-medium text-blue-700 dark:text-blue-300">
                            {call.routed_to}
                          </span>
                        ) : (
                          <span className="text-muted-foreground text-xs">Unrouted</span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-xs text-muted-foreground whitespace-nowrap">
                        {call.duration_s != null ? (
                          <span className="inline-flex items-center gap-1">
                            <Clock size={12} />
                            {Math.floor(call.duration_s / 60)}:{String(call.duration_s % 60).padStart(2, "0")}
                          </span>
                        ) : "—"}
                      </td>
                      <td className="px-3 py-2 text-xs text-muted-foreground whitespace-nowrap">
                        {new Date(call.created_at).toLocaleString("en-US", {
                          month: "short",
                          day: "numeric",
                          hour: "numeric",
                          minute: "2-digit",
                          hour12: true,
                        })}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </CollapsibleSection>

      {/* ── Mainline ── */}
      <CollapsibleSection
        icon={<Phone size={18} />}
        title="Mainline"
        subtitle={mainlineNumber ? mainlineNumber.twilio_number : "Not configured"}
        open={mainlineOpen}
        onToggle={() => setMainlineOpen((v) => !v)}
      >
        <div className="px-5 pb-4 space-y-3">
          {/* Number */}
          <div className="rounded-md border border-border px-3 py-2">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">Main Line</span>
              <div className="flex items-center gap-2">
                {mainlineNumber ? (
                  <>
                    <span className="text-xs font-mono text-foreground">{mainlineNumber.twilio_number}</span>
                    <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-medium text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400">Active</span>
                    {mainlineNumber.shaken_stir_status === "verified" ? (
                      <span className="flex items-center gap-0.5 rounded-full bg-blue-100 px-2 py-0.5 text-[10px] font-medium text-blue-700 dark:bg-blue-900/30 dark:text-blue-400">
                        <ShieldCheck size={10} /> Verified
                      </span>
                    ) : mainlineNumber.shaken_stir_status === "pending" ? (
                      <span className="flex items-center gap-0.5 rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-medium text-amber-700 dark:bg-amber-900/30 dark:text-amber-400">
                        <Loader2 size={10} className="animate-spin" /> Pending
                      </span>
                    ) : mainlineNumber.id ? (
                      <button
                        type="button"
                        onClick={() => handleVerifyLine(mainlineNumber.id!)}
                        disabled={verifyingLineId === mainlineNumber.id}
                        className="flex items-center gap-0.5 rounded-full bg-red-50 px-2 py-0.5 text-[10px] font-medium text-red-600 hover:bg-red-100 transition-colors dark:bg-red-900/20 dark:text-red-400 dark:hover:bg-red-900/30"
                      >
                        {verifyingLineId === mainlineNumber.id ? (
                          <><Loader2 size={10} className="animate-spin" /> Verifying…</>
                        ) : (
                          <><ShieldAlert size={10} /> Unverified</>
                        )}
                      </button>
                    ) : null}
                  </>
                ) : mainlineAction === "idle" ? (
                  <>
                    <span className="text-xs text-muted-foreground/50">Not configured</span>
                    <button
                      type="button"
                      onClick={() => { setMainlineAction("manual"); setMainlineDraft(""); }}
                      className="rounded border border-border px-2 py-0.5 text-[10px] font-medium text-muted-foreground hover:bg-muted transition-colors"
                    >
                      Enter number
                    </button>
                    <button
                      type="button"
                      onClick={() => { openChatWithMessage("I need to set up a main line phone number through Twilio."); }}
                      className="rounded border border-primary/30 bg-primary/5 px-2 py-0.5 text-[10px] font-medium text-primary hover:bg-primary/10 transition-colors"
                    >
                      Add via Twilio
                    </button>
                  </>
                ) : null}
              </div>
            </div>
            {mainlineAction === "manual" && !mainlineNumber && (
              <div className="mt-2 flex items-center gap-1.5">
                <input
                  type="tel"
                  value={mainlineDraft}
                  onChange={(e) => setMainlineDraft(e.target.value)}
                  placeholder="+1 (555) 123-4567"
                  className="flex-1 rounded border border-border bg-background px-2.5 py-1 text-sm outline-none focus:border-primary transition-colors font-mono"
                  autoFocus
                />
                <button
                  type="button"
                  onClick={() => {
                    if (mainlineDraft.trim()) {
                      openChatWithMessage(`Please set up ${mainlineDraft.trim()} as my main line number.`);
                      setMainlineAction("idle");
                    }
                  }}
                  className="rounded bg-primary px-2 py-1 text-[10px] font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
                >
                  <Check size={12} />
                </button>
                <button
                  type="button"
                  onClick={() => setMainlineAction("idle")}
                  className="rounded border border-border px-2 py-1 text-[10px] text-muted-foreground hover:bg-muted transition-colors"
                >
                  <X size={12} />
                </button>
              </div>
            )}
          </div>

          {/* Verification warning */}
          {mainlineNumber && mainlineNumber.shaken_stir_status === "unverified" && (
            <div className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 dark:border-amber-800 dark:bg-amber-900/20">
              <ShieldAlert size={14} className="mt-0.5 shrink-0 text-amber-600 dark:text-amber-400" />
              <div className="text-[11px] text-amber-800 dark:text-amber-300">
                <span className="font-medium">Calls may be blocked.</span> Your number doesn't have SHAKEN/STIR "A" attestation — carriers may flag it as spam. Click <strong>Unverified</strong> above to start verification.
              </div>
            </div>
          )}

          {/* Forward All Calls toggle */}
          {(() => {
            const forwardAll = phoneSettings?.forward_all_calls ?? true;
            const hasDeptRouting = deptConfig.some((d) => d.enabled && d.forward_number);
            const hasDefaultFwd = !!phoneSettings?.default_forward_number;
            const locked = !hasDeptRouting; // locked ON until at least one dept has a forwarding number

            return (
              <div className="rounded-md border border-border px-3 py-2 space-y-1.5">
                <button
                  type="button"
                  onClick={() => {
                    if (locked) return;
                    saveSettings({ forward_all_calls: !forwardAll });
                  }}
                  className={cn(
                    "flex w-full items-center justify-between rounded px-1 py-1 transition-colors",
                    locked ? "opacity-50 cursor-not-allowed" : "hover:bg-muted/60",
                  )}
                >
                  <span className="text-sm font-medium">Forward all calls</span>
                  <div
                    className={cn(
                      "relative h-5 w-9 rounded-full transition-colors",
                      forwardAll ? "bg-primary" : "bg-muted-foreground/30",
                    )}
                  >
                    <div
                      className={cn(
                        "absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform",
                        forwardAll ? "translate-x-4" : "translate-x-0.5",
                      )}
                    />
                  </div>
                </button>
                {/* Status messages */}
                {forwardAll && hasDefaultFwd && hasDeptRouting && (
                  <div className="flex items-center gap-1.5 rounded-md bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-900 px-2.5 py-1.5">
                    <div className="h-1.5 w-1.5 rounded-full bg-amber-500 shrink-0" />
                    <p className="text-xs text-amber-700 dark:text-amber-400">
                      IVR is bypassed — all calls forward directly to {phoneSettings?.default_forward_number}.
                    </p>
                  </div>
                )}
                {forwardAll && !hasDefaultFwd && (
                  <div className="flex items-center gap-1.5 rounded-md bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-900 px-2.5 py-1.5">
                    <div className="h-1.5 w-1.5 rounded-full bg-red-500 shrink-0" />
                    <p className="text-xs text-red-700 dark:text-red-400">
                      Set a default forwarding number below — calls have nowhere to go.
                    </p>
                  </div>
                )}
                {!forwardAll && (
                  <p className="text-[10px] text-muted-foreground px-1">
                    Calls go through IVR — greeting, AI routing, then department forwarding.
                  </p>
                )}
                {locked && (
                  <p className="text-[10px] text-muted-foreground/70 italic px-1">
                    Set up at least one department with a forwarding number to unlock IVR mode.
                  </p>
                )}
              </div>
            );
          })()}

          {/* Default Forwarding Number */}
          <div className="rounded-md border border-border px-3 py-2">
            <EditableText
              label="Default Forwarding Number"
              value={phoneSettings?.default_forward_number ?? null}
              placeholder="+1 (555) 123-4567"
              onSave={(v) => saveSettings({ default_forward_number: v })}
            />
          </div>


        </div>
      </CollapsibleSection>

      {/* ── Department Lines ── */}
      <CollapsibleSection
        icon={<PhoneForwarded size={18} />}
        title="Department Lines"
        subtitle={`${deptConfig.filter((d) => d.forward_number).length} forwarding`}
        open={deptLinesOpen}
        onToggle={() => setDeptLinesOpen((v) => !v)}
        warning={(() => {
          const forwardAll = phoneSettings?.forward_all_calls ?? true;
          const hasDeptFwd = deptConfig.some((d) => d.enabled && d.forward_number);
          if (forwardAll && !hasDeptFwd) return "Forward-all is on \u2022 no dept numbers set";
          if (forwardAll) return "Forward-all is on \u2014 turn it off to use dept routing";
          if (!hasDeptFwd) return "No departments have forwarding numbers";
          return null;
        })()}
      >
        <div className="px-5 pb-4">
          {deptConfig.length > 0 ? (
            <div className="space-y-1.5">
              {deptConfig.map((dept) => {
                const hasForward = !!dept.forward_number;
                const isSelecting = editingDeptId === dept.department_id;
                const isConfirmingDisconnect = confirmDisconnectDeptId === dept.department_id;
                // Find available Twilio numbers (not already used as mainline or by other depts)
                // Exclude mainline, other dept forwards, and tracking numbers
                const trackingNumberSet = new Set((trackingNumbers ?? []).map((t) => t.twilio_number));
                const usedNumbers = new Set([
                  mainlineNumber?.twilio_number,
                  ...deptConfig.filter((d) => d.department_id !== dept.department_id && d.forward_number).map((d) => d.forward_number),
                ].filter(Boolean));
                const availableTwilioNumbers = (twilioNumbers ?? []).filter(
                  (tn) => !usedNumbers.has(tn.phone_number) && !trackingNumberSet.has(tn.phone_number),
                );
                const allTwilioSet = new Set((twilioNumbers ?? []).map((tn) => tn.phone_number));
                const isTwilioOwned = hasForward && allTwilioSet.has(dept.forward_number!);

                return (
                  <div key={dept.department_id ?? dept.name} className={cn("rounded-md border border-border px-3 py-2 transition-opacity", !dept.enabled && "opacity-40")}>
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={() => toggleDept(dept.department_id)}
                          className={cn(
                            "relative inline-flex h-4 w-7 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors",
                            dept.enabled ? "bg-primary" : "bg-muted-foreground/30",
                          )}
                          title={dept.enabled ? "Disable routing" : "Enable routing"}
                        >
                          <span className={cn("pointer-events-none inline-block h-3 w-3 rounded-full bg-white shadow-sm transition-transform", dept.enabled ? "translate-x-3" : "translate-x-0")} />
                        </button>
                        <span className="text-sm font-medium">{dept.name}</span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        {hasForward ? (
                          <span className="text-xs font-mono text-foreground">{dept.forward_number}</span>
                        ) : (
                          <span className="text-xs text-muted-foreground/50">Uses mainline</span>
                        )}
                      </div>
                    </div>

                    {/* Disconnect confirmation */}
                    {isConfirmingDisconnect && hasForward && (
                      <div className="mt-2 rounded-md border border-red-200 dark:border-red-800 bg-red-50/50 dark:bg-red-900/10 px-3 py-2">
                        <p className="text-xs text-muted-foreground mb-2">
                          Disconnect <span className="font-mono font-medium text-foreground">{dept.forward_number}</span> from {dept.name}?
                        </p>
                        <div className="flex items-center gap-1.5">
                          <button
                            type="button"
                            onClick={() => {
                              saveDeptForwardNumber(dept.department_id, "");
                              setConfirmDisconnectDeptId(null);
                            }}
                            className="rounded border border-border px-2 py-0.5 text-[10px] font-medium text-muted-foreground hover:bg-muted transition-colors"
                          >
                            Disconnect only
                          </button>
                          {isTwilioOwned && (
                            <button
                              type="button"
                              onClick={() => {
                                openChatWithMessage(`Please disconnect and delete the Twilio number ${dept.forward_number} from the ${dept.name} department.`);
                                saveDeptForwardNumber(dept.department_id, "");
                                setConfirmDisconnectDeptId(null);
                              }}
                              className="rounded bg-red-500 px-2 py-0.5 text-[10px] font-medium text-white hover:bg-red-600 transition-colors"
                            >
                              Delete from Twilio
                            </button>
                          )}
                          <button
                            type="button"
                            onClick={() => setConfirmDisconnectDeptId(null)}
                            className="rounded p-0.5 text-muted-foreground hover:bg-muted transition-colors"
                          >
                            <X size={11} />
                          </button>
                        </div>
                      </div>
                    )}

                    {/* Select from available Twilio numbers or enter manual */}
                    {isSelecting && (
                      <div className="mt-2 space-y-1">
                        {!deptManualInput ? (
                          <>
                            {availableTwilioNumbers.map((tn) => (
                              <button
                                key={tn.sid}
                                type="button"
                                onClick={() => {
                                  saveDeptForwardNumber(dept.department_id, tn.phone_number);
                                  setEditingDeptId(null);
                                }}
                                className="flex w-full items-center justify-between rounded border border-border px-2 py-1 text-xs hover:bg-muted transition-colors"
                              >
                                <span className="font-mono">{tn.phone_number}</span>
                                <span className="text-muted-foreground">{tn.friendly_name}</span>
                              </button>
                            ))}
                            <button
                              type="button"
                              onClick={() => {
                                openChatWithMessage(`I need a new Twilio phone number for the ${dept.name} department forwarding line.`);
                                setEditingDeptId(null);
                              }}
                              className="flex w-full items-center gap-1 rounded border border-dashed border-primary/30 px-2 py-1 text-[10px] font-medium text-primary hover:bg-primary/5 transition-colors"
                            >
                              <Plus size={9} /> Provision new Twilio number
                            </button>
                            <button
                              type="button"
                              onClick={() => { setDeptManualInput(true); setDeptNumberDraft(""); }}
                              className="flex w-full items-center gap-1 rounded border border-dashed border-border px-2 py-1 text-[10px] font-medium text-muted-foreground hover:bg-muted/50 transition-colors"
                            >
                              <Pencil size={9} /> Enter manual number
                            </button>
                            <button
                              type="button"
                              onClick={() => setEditingDeptId(null)}
                              className="text-[10px] text-muted-foreground hover:text-foreground transition-colors"
                            >
                              Cancel
                            </button>
                          </>
                        ) : (
                          <div className="flex items-center gap-1.5">
                            <input
                              type="tel"
                              value={deptNumberDraft}
                              onChange={(e) => setDeptNumberDraft(e.target.value)}
                              placeholder="+1 (555) 000-0000"
                              className="w-40 rounded border border-border bg-background px-2 py-0.5 text-xs outline-none focus:border-primary transition-colors font-mono"
                              autoFocus
                              onKeyDown={(e) => {
                                if (e.key === "Enter" && deptNumberDraft.trim()) {
                                  saveDeptForwardNumber(dept.department_id, deptNumberDraft.trim());
                                  setEditingDeptId(null);
                                  setDeptManualInput(false);
                                }
                                if (e.key === "Escape") { setDeptManualInput(false); }
                              }}
                            />
                            <button
                              type="button"
                              onClick={() => {
                                if (deptNumberDraft.trim()) {
                                  saveDeptForwardNumber(dept.department_id, deptNumberDraft.trim());
                                  setEditingDeptId(null);
                                  setDeptManualInput(false);
                                }
                              }}
                              className="rounded p-0.5 text-primary hover:bg-primary/10 transition-colors"
                            >
                              <Check size={12} />
                            </button>
                            <button
                              type="button"
                              onClick={() => setDeptManualInput(false)}
                              className="text-[10px] text-muted-foreground hover:text-foreground transition-colors"
                            >
                              ← Back
                            </button>
                          </div>
                        )}
                      </div>
                    )}

                    {/* Action buttons */}
                    {!isSelecting && !isConfirmingDisconnect && (
                      <div className="mt-1.5 flex items-center gap-2">
                        <button
                          type="button"
                          onClick={() => { setEditingDeptId(dept.department_id); setConfirmDisconnectDeptId(null); setDeptManualInput(false); }}
                          className="flex items-center gap-1 text-[10px] text-muted-foreground hover:text-primary transition-colors"
                        >
                          <Plus size={9} /> Connect number
                        </button>
                        {hasForward && (
                          <button
                            type="button"
                            onClick={() => { setConfirmDisconnectDeptId(dept.department_id); setEditingDeptId(null); }}
                            className="flex items-center gap-1 text-[10px] text-muted-foreground hover:text-red-500 transition-colors"
                          >
                            <Power size={9} /> Disconnect
                          </button>
                        )}
                      </div>
                    )}

                    {/* SMS Notifications toggle */}
                    {dept.enabled && hasForward && !isSelecting && !isConfirmingDisconnect && (
                      <div className="mt-2 flex items-center gap-2">
                        <button
                          type="button"
                          onClick={() => {
                            if (!a2pStatus?.ready && !dept.sms_enabled) {
                              setShowSmsInfo(true);
                              return;
                            }
                            toggleDeptSms(dept.department_id);
                          }}
                          className={cn(
                            "relative inline-flex h-4 w-7 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors",
                            dept.sms_enabled ? "bg-primary" : "bg-muted-foreground/30",
                          )}
                          title={dept.sms_enabled ? "Disable SMS notifications" : "Enable SMS notifications"}
                        >
                          <span className={cn(
                            "pointer-events-none inline-block h-3 w-3 rounded-full bg-white shadow transition-transform",
                            dept.sms_enabled ? "translate-x-3" : "translate-x-0",
                          )} />
                        </button>
                        <span className="text-[10px] text-muted-foreground">SMS notifications</span>
                        <button
                          type="button"
                          onClick={() => setShowSmsInfo(true)}
                          className="text-muted-foreground hover:text-primary transition-colors"
                          title="SMS setup info"
                        >
                          <Info size={11} />
                        </button>
                        {dept.sms_enabled && !a2pStatus?.ready && (
                          <span className="text-[9px] text-amber-600 dark:text-amber-400 font-medium">Pending approval</span>
                        )}
                      </div>
                    )}

                  </div>
                );
              })}
            </div>
          ) : (
            <p className="text-xs text-muted-foreground text-center py-2">No departments configured</p>
          )}
        </div>
      </CollapsibleSection>

      {/* ── SMS Info Popup ── */}
      {showSmsInfo && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={() => setShowSmsInfo(false)}>
          <div className="w-full max-w-md rounded-lg border border-border bg-background p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold">SMS Notifications Setup</h3>
              <button onClick={() => setShowSmsInfo(false)} className="text-muted-foreground hover:text-foreground text-lg leading-none">&times;</button>
            </div>
            <div className="space-y-3 text-xs text-muted-foreground">
              <p>
                When enabled, an SMS is sent to the department's forwarding number after each routed call with the <span className="font-medium text-foreground">caller's name</span> and <span className="font-medium text-foreground">reason for calling</span>.
              </p>
              <div className="rounded-md bg-muted/50 border border-border px-3 py-2">
                <p className="font-medium text-foreground text-[11px] mb-1">A2P 10DLC Campaign Required</p>
                <p>
                  US carriers require A2P (Application-to-Person) registration for business SMS. This involves:
                </p>
                <ol className="list-decimal ml-4 mt-1 space-y-0.5">
                  <li>Register your brand in Twilio Console → Messaging → Regulatory Compliance → A2P</li>
                  <li>Create a campaign (use case: "Mixed" or "Customer Care")</li>
                  <li>Add your phone numbers to the Messaging Service linked to the campaign</li>
                </ol>
                <p className="mt-1.5">Approval typically takes <span className="font-medium text-foreground">1–7 business days</span>.</p>
              </div>
              <div className="flex items-center gap-2">
                <div className={cn("h-2 w-2 rounded-full shrink-0", a2pStatus?.ready ? "bg-green-500" : "bg-amber-500")} />
                <span className="text-[11px]">
                  Campaign status: <span className="font-medium text-foreground">{a2pStatus?.campaign_status ?? "checking..."}</span>
                  {a2pStatus?.ready && " — Ready to send"}
                </span>
              </div>
            </div>
            <div className="mt-4 flex justify-end">
              <button
                onClick={() => setShowSmsInfo(false)}
                className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
              >
                Got it
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Tracking Numbers ── */}
      <CollapsibleSection
        icon={<Hash size={18} />}
        title="Tracking Numbers"
        subtitle={`${campaignNumbers.length} campaign${campaignNumbers.length !== 1 ? "s" : ""}`}
        open={trackingNumbersOpen}
        onToggle={() => setTrackingNumbersOpen((v) => !v)}
      >
        <div className="px-5 pb-4 space-y-1.5">
            {campaignNumbers.length > 0 ? (
              campaignNumbers.map((tn) => (
                <div key={tn.id} className="group rounded-md border border-border px-3 py-1.5">
                  {confirmRemoveTrackingId === tn.id ? (
                    <div className="flex items-center justify-between py-0.5">
                      <p className="text-xs text-muted-foreground">Remove <span className="font-medium text-foreground font-mono">{tn.twilio_number}</span> ({tn.campaign_name})?</p>
                      <div className="flex items-center gap-1">
                        <button
                          type="button"
                          onClick={() => {
                            openChatWithMessage(`Please remove the tracking number ${tn.twilio_number} (${tn.campaign_name}).`);
                            setConfirmRemoveTrackingId(null);
                          }}
                          className="rounded bg-red-500 px-2 py-0.5 text-[10px] font-medium text-white hover:bg-red-600 transition-colors"
                        >
                          Remove
                        </button>
                        <button
                          type="button"
                          onClick={() => setConfirmRemoveTrackingId(null)}
                          className="rounded border border-border px-2 py-0.5 text-[10px] text-muted-foreground hover:bg-muted transition-colors"
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium">{tn.campaign_name}</span>
                        {tn.channel && (
                          <span className="text-[10px] text-muted-foreground">{tn.channel}</span>
                        )}
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-mono text-foreground">{tn.twilio_number}</span>
                        {tn.shaken_stir_status === "verified" ? (
                          <span className="flex items-center gap-0.5 rounded-full bg-blue-100 px-1.5 py-0.5 text-[9px] font-medium text-blue-700 dark:bg-blue-900/30 dark:text-blue-400">
                            <ShieldCheck size={9} /> Verified
                          </span>
                        ) : tn.shaken_stir_status === "pending" ? (
                          <span className="flex items-center gap-0.5 rounded-full bg-amber-100 px-1.5 py-0.5 text-[9px] font-medium text-amber-700 dark:bg-amber-900/30 dark:text-amber-400">
                            <Loader2 size={9} className="animate-spin" /> Pending
                          </span>
                        ) : tn.id ? (
                          <button
                            type="button"
                            onClick={() => handleVerifyLine(tn.id!)}
                            disabled={verifyingLineId === tn.id}
                            className="flex items-center gap-0.5 rounded-full bg-red-50 px-1.5 py-0.5 text-[9px] font-medium text-red-600 hover:bg-red-100 transition-colors dark:bg-red-900/20 dark:text-red-400"
                          >
                            {verifyingLineId === tn.id ? (
                              <><Loader2 size={9} className="animate-spin" /> Verifying…</>
                            ) : (
                              <><ShieldAlert size={9} /> Verify</>
                            )}
                          </button>
                        ) : null}
                        <button
                          type="button"
                          onClick={() => setConfirmRemoveTrackingId(tn.id)}
                          className="rounded p-0.5 text-muted-foreground/0 group-hover:text-muted-foreground/50 hover:!text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 transition-all"
                          title="Remove number"
                        >
                          <Trash2 size={12} />
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              ))
            ) : (
              <p className="text-xs text-muted-foreground text-center py-2">
                {isConnected ? "No tracking numbers configured" : "Connect Twilio to add tracking numbers"}
              </p>
            )}

            {/* Add tracking number via Twilio */}
            <div className="pt-1">
              <button
                type="button"
                onClick={() => openChatWithMessage("I need to add a new tracking number through Twilio for a campaign.")}
                className="flex items-center gap-1 rounded border border-primary/30 bg-primary/5 px-2 py-1 text-[10px] font-medium text-primary hover:bg-primary/10 transition-colors"
              >
                <Plus size={10} /> Add via Twilio
              </button>
            </div>
          </div>
      </CollapsibleSection>

      {/* ── IVR Section ── */}
      <CollapsibleSection
        icon={<Volume2 size={18} />}
        title="IVR"
        subtitle="Greeting, voice, hold & recording"
        open={ivrOpen}
        onToggle={() => setIvrOpen((v) => !v)}
      >
        <div className="px-5 pb-4">
          <div className="grid gap-4 sm:grid-cols-2 items-start">
            {/* Greeting & Voice */}
            <SettingsCard icon={<Volume2 size={14} />} title="Greeting & Voice">
              <div className="space-y-3">
                <EditableText
                  label="Greeting"
                  value={phoneSettings?.greeting_text ?? null}
                  placeholder="No greeting configured"
                  multiline
                  onSave={(v) => saveSettings({ greeting_text: v })}
                />
                <VoiceSelector
                  value={phoneSettings?.voice_name ?? "Polly.Joanna-Neural"}
                  onSave={(v) => saveSettings({ voice_name: v })}
                />
              </div>
            </SettingsCard>

            {/* Hold Message */}
            <SettingsCard icon={<MessageSquare size={14} />} title="Hold Message">
              <div className="space-y-2">
                <EditableText
                  label="Hold Message"
                  value={phoneSettings?.hold_message ?? null}
                  placeholder="Please hold while we connect you to the next available representative."
                  multiline
                  onSave={(v) => saveSettings({ hold_message: v })}
                />
                <p className="text-[10px] text-muted-foreground">
                  Plays to callers while they wait on hold.
                </p>
              </div>
            </SettingsCard>

            {/* Call Recording */}
            <SettingsCard
              icon={<Mic size={14} />}
              title="Call Recording"
              warning={!(phoneSettings?.transcription_enabled) ? "Transcription off \u2014 needed for IVR" : null}
            >
            <div className="space-y-2">
              <ToggleSwitch
                label="Record & analyze calls"
                enabled={phoneSettings?.recording_enabled ?? false}
                onToggle={() => {
                  const next = !phoneSettings?.recording_enabled;
                  saveSettings({ recording_enabled: next, transcription_enabled: next });
                }}
              />
              {(() => {
                const routingOn = phoneSettings?.recording_enabled;
                const forwardAll = phoneSettings?.forward_all_calls ?? true;
                const hasEnabledDepts = deptConfig.some((d) => d.enabled && d.forward_number);

                if (forwardAll) {
                  return (
                    <p className="text-[10px] text-muted-foreground mt-1">
                      Forward-all is on — IVR is bypassed. Toggle it off in Mainline to use AI routing.
                    </p>
                  );
                }
                if (routingOn && !hasEnabledDepts) {
                  return (
                    <div className="flex items-center gap-1.5 rounded-md bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-900 px-2.5 py-1.5 mt-1">
                      <div className="h-1.5 w-1.5 rounded-full bg-red-500 shrink-0" />
                      <p className="text-xs text-red-700 dark:text-red-400">
                        Enable at least one department with a forwarding number for AI routing.
                      </p>
                    </div>
                  );
                }
                if (routingOn) {
                  return (
                    <p className="text-[10px] text-muted-foreground mt-1">
                      Calls are recorded and routed to departments via AI.
                    </p>
                  );
                }
                // Routing OFF but forward-all is also OFF — unusual state
                return (
                  <p className="text-[10px] text-muted-foreground mt-1">
                    Recording is off. Enable to start AI-powered call routing.
                  </p>
                );
              })()}
            </div>
            </SettingsCard>

            {/* Business Hours & After-Hours */}
            <SettingsCard icon={<Clock size={14} />} title="Business Hours">
            <div className="space-y-3">
              <div className="space-y-3">
                <div className="flex items-center gap-4">
                  <div>
                    <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Open</label>
                    <TimePicker
                      value={phoneSettings?.business_hours_start ?? null}
                      onChange={(v) => saveSettings({ business_hours_start: v })}
                    />
                  </div>
                  <span className="mt-5 text-muted-foreground">to</span>
                  <div>
                    <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Close</label>
                    <TimePicker
                      value={phoneSettings?.business_hours_end ?? null}
                      onChange={(v) => saveSettings({ business_hours_end: v })}
                    />
                  </div>
                </div>
                <div>
                  <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Timezone</label>
                  <select
                    value={phoneSettings?.business_timezone ?? "America/Chicago"}
                    onChange={(e) => saveSettings({ business_timezone: e.target.value })}
                    className="rounded border border-border bg-background px-2.5 py-1.5 text-sm outline-none focus:border-primary transition-colors"
                  >
                    <option value="America/New_York">Eastern</option>
                    <option value="America/Chicago">Central</option>
                    <option value="America/Denver">Mountain</option>
                    <option value="America/Los_Angeles">Pacific</option>
                    <option value="America/Anchorage">Alaska</option>
                    <option value="Pacific/Honolulu">Hawaii</option>
                  </select>
                </div>
              </div>

              {/* After-Hours Toggle + Action */}
              {(() => {
                const hasHours = !!(phoneSettings?.business_hours_start && phoneSettings?.business_hours_end);
                const action = phoneSettings?.after_hours_action ?? "message";
                const hasMessage = !!phoneSettings?.after_hours_message;
                const hasForwardNum = !!phoneSettings?.after_hours_forward_number;
                return (
                  <div className="space-y-2 pt-2 border-t border-border">
                    <ToggleSwitch
                      label="After-hours handling"
                      enabled={phoneSettings?.after_hours_enabled ?? false}
                      onToggle={() => {
                        if (!phoneSettings?.after_hours_enabled && !hasHours) return;
                        saveSettings({ after_hours_enabled: !phoneSettings?.after_hours_enabled });
                      }}
                    />
                    {!hasHours && (
                      <div className="flex items-center gap-1.5 rounded-md bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-900 px-2.5 py-1.5">
                        <div className="h-1.5 w-1.5 rounded-full bg-red-500 shrink-0" />
                        <p className="text-xs text-red-700 dark:text-red-400">
                          Set business hours above before enabling after-hours.
                        </p>
                      </div>
                    )}

                    {/* Action selector + fields — only visible when toggled on */}
                    {(phoneSettings?.after_hours_enabled) && (
                      <>
                        <div>
                          <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-1">After-hours action</p>
                          <div className="flex gap-2">
                            <button
                              onClick={() => saveSettings({ after_hours_action: "message" })}
                              className={cn(
                                "flex-1 rounded-md border px-3 py-1.5 text-xs font-medium transition-colors",
                                action === "message"
                                  ? "border-primary bg-primary/10 text-primary"
                                  : "border-border bg-background text-muted-foreground hover:bg-muted",
                              )}
                            >
                              Play message
                            </button>
                            <button
                              onClick={() => saveSettings({ after_hours_action: "forward" })}
                              className={cn(
                                "flex-1 rounded-md border px-3 py-1.5 text-xs font-medium transition-colors",
                                action === "forward"
                                  ? "border-primary bg-primary/10 text-primary"
                                  : "border-border bg-background text-muted-foreground hover:bg-muted",
                              )}
                            >
                              Forward calls
                            </button>
                          </div>
                          <p className="text-[10px] text-muted-foreground mt-1">
                            {action === "message"
                              ? "Plays your after-hours message then hangs up — skips the IVR."
                              : "Forwards calls directly to a number after hours — skips the IVR."}
                          </p>
                        </div>

                        {/* Message action fields */}
                        {action === "message" && (
                          <>
                            {hasHours && !hasMessage && (
                              <div className="flex items-center gap-1.5 rounded-md bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-900 px-2.5 py-1.5">
                                <div className="h-1.5 w-1.5 rounded-full bg-red-500 shrink-0" />
                                <p className="text-xs text-red-700 dark:text-red-400">
                                  Set an after-hours message below before enabling.
                                </p>
                              </div>
                            )}
                            <EditableText
                              label="After-Hours Message"
                              value={phoneSettings?.after_hours_message ?? null}
                              placeholder="We're currently closed. Our hours are Monday through Friday, 9 AM to 5 PM. Please leave a message."
                              multiline
                              onSave={(v) => saveSettings({ after_hours_message: v })}
                            />
                          </>
                        )}

                        {/* Forward action fields */}
                        {action === "forward" && (
                          <>
                            {hasHours && !hasForwardNum && (
                              <div className="flex items-center gap-1.5 rounded-md bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-900 px-2.5 py-1.5">
                                <div className="h-1.5 w-1.5 rounded-full bg-red-500 shrink-0" />
                                <p className="text-xs text-red-700 dark:text-red-400">
                                  Set a forward number below before enabling.
                                </p>
                              </div>
                            )}
                            <EditableText
                              label="After-Hours Forward Number"
                              value={phoneSettings?.after_hours_forward_number ?? null}
                              placeholder="+19405551234"
                              onSave={(v) => saveSettings({ after_hours_forward_number: v })}
                            />
                          </>
                        )}
                      </>
                    )}
                  </div>
                );
              })()}
            </div>
            </SettingsCard>
          </div>
        </div>
      </CollapsibleSection>

      {/* ── Call Flow Section ── */}
      <CollapsibleSection
        icon={<GitBranch size={18} />}
        title="Call Flow"
        subtitle="Routing & department branches"
        open={callFlowOpen}
        onToggle={() => setCallFlowOpen((v) => !v)}
        warning={(() => {
          const warnings: string[] = [];
          const forwardAll = phoneSettings?.forward_all_calls ?? true;
          if (forwardAll) warnings.push("Calls are being forwarded — routing is bypassed");
          const afterHoursOn = phoneSettings?.after_hours_enabled ?? false;
          if (afterHoursOn) {
            const action = phoneSettings?.after_hours_action ?? "message";
            if (action === "forward") {
              warnings.push(phoneSettings?.after_hours_forward_number
                ? "After-hours forwarding is active"
                : "After-hours forwarding enabled but no number set");
            } else {
              warnings.push(phoneSettings?.after_hours_message
                ? "After-hours message is active"
                : "After-hours enabled but no message set");
            }
          }
          return warnings.length ? warnings.join(" · ") : null;
        })()}
      >
        <CallFlowSection phoneSettings={phoneSettings ?? null} businessId={bizId} />
      </CollapsibleSection>


    </div>
  );
}

// ── Per-Department WhatsApp Connection ──

function DeptWhatsApp({ dept, bizId, twilioNumber, onUpdate }: {
  dept: DepartmentRoutingRule;
  bizId: string;
  twilioNumber: string | null;
  onUpdate: () => void;
}) {
  const [showSetup, setShowSetup] = useState(false);
  const [displayName, setDisplayName] = useState("");
  const [verCode, setVerCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const senderStatus = dept.whatsapp_sender_status || "none";
  const isOnline = senderStatus === "ONLINE";
  const isPending = ["CREATING", "PENDING_VERIFICATION", "VERIFYING", "TWILIO_REVIEW"].includes(senderStatus);
  const needsOtp = senderStatus === "PENDING_VERIFICATION";
  const isNone = senderStatus === "none" && !dept.whatsapp_sender_sid;

  const handleRegister = async () => {
    if (!displayName.trim() || !twilioNumber) return;
    setBusy(true);
    setError(null);
    try {
      await registerWhatsAppSender({
        business_id: bizId,
        department_id: dept.department_id,
        phone_number: twilioNumber,
        display_name: displayName.trim(),
      });
      onUpdate();
      setShowSetup(false);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || "Registration failed");
    } finally {
      setBusy(false);
    }
  };

  const handleVerify = async () => {
    if (!verCode.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await verifyWhatsAppSender({
        business_id: bizId,
        department_id: dept.department_id,
        verification_code: verCode.trim(),
      });
      onUpdate();
      setVerCode("");
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || "Verification failed");
    } finally {
      setBusy(false);
    }
  };

  const handleRefresh = async () => {
    setBusy(true);
    setError(null);
    try {
      await refreshWhatsAppStatus(bizId, dept.department_id);
      onUpdate();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Refresh failed");
    } finally {
      setBusy(false);
    }
  };

  const handleTest = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await sendWhatsAppTest(bizId, dept.department_id);
      if (res.status === "sent") {
        setError(null);
      } else {
        setError("Test message failed to send");
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Test failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mt-2 border-t border-border/50 pt-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <MessageSquare size={11} className={isOnline ? "text-green-600" : "text-muted-foreground"} />
          <span className="text-[10px] text-muted-foreground">WhatsApp</span>
          {isOnline && <span className="text-[9px] font-medium text-green-600 bg-green-50 dark:bg-green-900/20 px-1 rounded">ONLINE</span>}
          {isPending && !needsOtp && <span className="text-[9px] font-medium text-amber-600 bg-amber-50 dark:bg-amber-900/20 px-1 rounded">{senderStatus}</span>}
          {needsOtp && <span className="text-[9px] font-medium text-blue-600 bg-blue-50 dark:bg-blue-900/20 px-1 rounded">NEEDS OTP</span>}
        </div>
        <div className="flex items-center gap-1">
          {isOnline && (
            <button type="button" onClick={handleTest} disabled={busy}
              className="text-[9px] text-green-600 hover:text-green-700 transition-colors disabled:opacity-50">
              {busy ? "Sending..." : "Test"}
            </button>
          )}
          {(isPending || isOnline) && (
            <button type="button" onClick={handleRefresh} disabled={busy}
              className="text-[9px] text-muted-foreground hover:text-primary transition-colors disabled:opacity-50">
              {busy ? <Loader2 size={9} className="animate-spin" /> : "Refresh"}
            </button>
          )}
          {isNone && (
            <button type="button" onClick={() => setShowSetup(!showSetup)}
              className="flex items-center gap-0.5 text-[9px] text-primary hover:text-primary/80 transition-colors">
              <Plus size={8} /> Connect
            </button>
          )}
        </div>
      </div>

      {/* OTP verification */}
      {needsOtp && (
        <div className="mt-1.5 flex items-center gap-1.5">
          <input
            type="text"
            value={verCode}
            onChange={(e) => setVerCode(e.target.value)}
            placeholder="Enter OTP code"
            className="w-24 rounded border border-border bg-background px-2 py-0.5 text-xs font-mono outline-none focus:border-primary"
            onKeyDown={(e) => { if (e.key === "Enter") handleVerify(); }}
          />
          <button type="button" onClick={handleVerify} disabled={busy || !verCode.trim()}
            className="rounded bg-primary px-2 py-0.5 text-[10px] font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
            Verify
          </button>
        </div>
      )}

      {/* Setup prerequisite note — always shown when no sender is registered */}
      {isNone && !showSetup && (
        <div className="mt-1.5 flex items-start gap-1.5 rounded bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-900 px-2 py-1.5">
          <AlertTriangle size={10} className="mt-0.5 shrink-0 text-amber-500" />
          <p className="text-[9px] text-amber-700 dark:text-amber-400 leading-relaxed">
            <span className="font-medium">Requires setup:</span> Before connecting WhatsApp, you must register a WhatsApp Business Account (WABA) in the{" "}
            <a href="https://console.twilio.com/us1/develop/sms/senders/whatsapp-senders" target="_blank" rel="noreferrer" className="underline hover:text-amber-900 dark:hover:text-amber-300">
              Twilio Console → WhatsApp Senders
            </a>.
          </p>
        </div>
      )}

      {/* Registration form */}
      {showSetup && isNone && !twilioNumber && (
        <p className="mt-1.5 text-[9px] text-amber-600">No Twilio number assigned — set up a mainline number first.</p>
      )}
      {showSetup && isNone && twilioNumber && (
        <div className="mt-1.5 space-y-1.5">
          <input
            type="text"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            placeholder="Business display name"
            className="w-full rounded border border-border bg-background px-2 py-1 text-xs outline-none focus:border-primary"
          />
          <p className="text-[9px] text-muted-foreground">
            Registers Twilio number <span className="font-mono">{twilioNumber}</span> as a WhatsApp sender.
            Notifications will be sent to <span className="font-mono">{dept.forward_number}</span>.
          </p>
          <div className="flex items-center gap-1.5">
            <button type="button" onClick={handleRegister} disabled={busy || !displayName.trim()}
              className="rounded bg-green-600 px-2 py-0.5 text-[10px] font-medium text-white hover:bg-green-700 disabled:opacity-50">
              {busy ? <Loader2 size={10} className="animate-spin" /> : "Register"}
            </button>
            <button type="button" onClick={() => setShowSetup(false)}
              className="text-[9px] text-muted-foreground hover:text-foreground">
              Cancel
            </button>
          </div>
        </div>
      )}

      {error && (
        <p className="mt-1 text-[9px] text-red-500">{error}</p>
      )}
    </div>
  );
}


// ── Time Picker (hour · minute · AM/PM) ──

function TimePicker({
  value,
  onChange,
}: {
  value: string | null; // "HH:MM" 24-h format or null
  onChange: (val: string | null) => void;
}) {
  // Parse "HH:MM" into 12-hour parts
  const parsed = (() => {
    if (!value) return { hour: "", minute: "00", ampm: "AM" };
    const [hStr, mStr] = value.split(":");
    const h24 = parseInt(hStr, 10);
    const ampm = h24 < 12 ? "AM" : "PM";
    const hour = h24 === 0 ? "12" : h24 > 12 ? String(h24 - 12) : String(h24);
    return { hour, minute: mStr ?? "00", ampm };
  })();

  const build = (hour: string, minute: string, ampm: string) => {
    if (!hour) { onChange(null); return; }
    let h24 = parseInt(hour, 10);
    if (ampm === "AM" && h24 === 12) h24 = 0;
    if (ampm === "PM" && h24 !== 12) h24 += 12;
    onChange(`${String(h24).padStart(2, "0")}:${minute}`);
  };

  const sel = "rounded border border-border bg-background px-2 py-1.5 text-sm outline-none focus:border-primary transition-colors";

  return (
    <div className="flex items-center gap-1">
      <select className={sel} value={parsed.hour} onChange={(e) => build(e.target.value, parsed.minute, parsed.ampm)}>
        <option value="">—</option>
        {Array.from({ length: 12 }, (_, i) => { const h = String(i + 1); return <option key={h} value={h}>{h}</option>; })}
      </select>
      <span className="text-muted-foreground font-mono">:</span>
      <select className={sel} value={parsed.minute} onChange={(e) => build(parsed.hour, e.target.value, parsed.ampm)}>
        {["00", "15", "30", "45"].map((m) => <option key={m} value={m}>{m}</option>)}
      </select>
      <select className={`${sel} font-semibold`} value={parsed.ampm} onChange={(e) => build(parsed.hour, parsed.minute, e.target.value)}>
        <option value="AM">AM</option>
        <option value="PM">PM</option>
      </select>
    </div>
  );
}

// ── Collapsible Section ──

function CollapsibleSection({
  icon,
  title,
  subtitle,
  open,
  onToggle,
  disabled,
  disabledMessage,
  warning,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  subtitle?: string;
  open: boolean;
  onToggle: () => void;
  disabled?: boolean;
  disabledMessage?: string;
  warning?: string | null;
  children: React.ReactNode;
}) {
  return (
    <div className={cn("rounded-lg border border-border bg-card transition-opacity", disabled && "opacity-50")}>
      <button
        type="button"
        onClick={disabled ? undefined : onToggle}
        className={cn(
          "flex w-full items-center justify-between px-5 py-4 text-left transition-colors",
          disabled ? "cursor-not-allowed" : "hover:bg-muted/50",
        )}
      >
        <span className="flex items-center gap-2.5">
          <span className={disabled ? "text-muted-foreground" : "text-primary"}>{icon}</span>
          <span className="font-semibold">{title}</span>
          {subtitle && (
            <span className="text-xs text-muted-foreground">{subtitle}</span>
          )}
          {!disabled && warning && (
            <span className="flex items-center gap-1 text-[10px] text-amber-600 dark:text-amber-400">
              <AlertTriangle size={12} /> {warning}
            </span>
          )}
          {disabled && disabledMessage && (
            <span className="text-[10px] text-muted-foreground/70 italic">{disabledMessage}</span>
          )}
        </span>
        <ChevronDown
          size={16}
          className={cn(
            "text-muted-foreground transition-transform duration-200",
            open && !disabled && "rotate-180",
          )}
        />
      </button>
      {open && !disabled && <div className="border-t border-border px-5 py-5">{children}</div>}
    </div>
  );
}

// ── Inline Editing Primitives ──

function EditableText({
  value,
  placeholder,
  onSave,
  multiline = false,
  label,
}: {
  value: string | null;
  placeholder: string;
  onSave: (val: string) => void;
  multiline?: boolean;
  label?: string;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value ?? "");
  const inputRef = useRef<HTMLTextAreaElement | HTMLInputElement>(null);

  useEffect(() => {
    if (editing) {
      setDraft(value ?? "");
      setTimeout(() => inputRef.current?.focus(), 0);
    }
  }, [editing, value]);

  const commit = () => {
    const trimmed = draft.trim();
    if (trimmed !== (value ?? "")) onSave(trimmed);
    setEditing(false);
  };

  const cancel = () => setEditing(false);

  if (editing) {
    return (
      <div className="space-y-1.5">
        {label && (
          <p className="text-[11px] font-medium text-muted-foreground">{label}</p>
        )}
        {multiline ? (
          <textarea
            ref={inputRef as React.RefObject<HTMLTextAreaElement>}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); commit(); }
              if (e.key === "Escape") cancel();
            }}
            rows={3}
            className="w-full rounded border border-primary/40 bg-background px-2.5 py-1.5 text-sm leading-relaxed outline-none focus:border-primary resize-none"
          />
        ) : (
          <input
            ref={inputRef as React.RefObject<HTMLInputElement>}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") commit();
              if (e.key === "Escape") cancel();
            }}
            className="w-full rounded border border-primary/40 bg-background px-2.5 py-1.5 text-sm outline-none focus:border-primary"
          />
        )}
        <div className="flex items-center gap-1.5">
          <button
            onClick={commit}
            className="flex items-center gap-1 rounded px-2 py-1 text-[11px] font-medium bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
          >
            <Check size={11} /> Save
          </button>
          <button
            onClick={cancel}
            className="flex items-center gap-1 rounded px-2 py-1 text-[11px] font-medium text-muted-foreground hover:bg-muted transition-colors"
          >
            <X size={11} /> Cancel
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="group">
      {label && (
        <p className="text-[11px] font-medium text-muted-foreground mb-0.5">{label}</p>
      )}
      <button
        type="button"
        onClick={() => setEditing(true)}
        className="flex w-full items-start gap-2 rounded px-1 py-0.5 text-left transition-colors hover:bg-muted/60"
      >
        <span className={cn("text-sm leading-relaxed flex-1", !value && "italic text-muted-foreground")}>
          {value || placeholder}
        </span>
        <Pencil size={11} className="mt-1 shrink-0 text-muted-foreground/0 group-hover:text-muted-foreground transition-colors" />
      </button>
    </div>
  );
}

function ToggleSwitch({
  label,
  enabled,
  onToggle,
}: {
  label: string;
  enabled: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      className="flex w-full items-center justify-between rounded px-1 py-1 transition-colors hover:bg-muted/60"
    >
      <span className="text-sm">{label}</span>
      <div
        className={cn(
          "relative h-5 w-9 rounded-full transition-colors",
          enabled ? "bg-emerald-500" : "bg-muted-foreground/30",
        )}
      >
        <div
          className={cn(
            "absolute top-0.5 h-4 w-4 rounded-full bg-white transition-transform shadow-sm",
            enabled ? "translate-x-4" : "translate-x-0.5",
          )}
        />
      </div>
    </button>
  );
}

// ── Settings Cards ──

function SettingsCard({
  icon,
  title,
  children,
  defaultOpen = false,
  warning,
}: {
  icon: React.ReactNode;
  title: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
  warning?: string | null;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="rounded-lg border border-border">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-4 py-3 text-left transition-colors hover:bg-muted/50"
      >
        <span className="flex items-center gap-2">
          <span className="text-primary">{icon}</span>
          <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            {title}
          </span>
          {warning && (
            <span className="flex items-center gap-1 text-[10px] text-amber-600 dark:text-amber-400 font-normal normal-case tracking-normal">
              <AlertTriangle size={11} /> {warning}
            </span>
          )}
        </span>
        <ChevronDown
          size={14}
          className={cn(
            "text-muted-foreground transition-transform duration-200",
            open && "rotate-180",
          )}
        />
      </button>
      {open && <div className="px-4 pb-4">{children}</div>}
    </div>
  );
}



function CallFlowSection({ phoneSettings, businessId }: { phoneSettings: PhoneSettingsRead | null; businessId: string }) {
  const routingRules = (phoneSettings?.departments_config ?? []).filter(
    (r: DepartmentRoutingRule) => r.name !== "IT",
  );
  const activeRules = routingRules.filter((r: DepartmentRoutingRule) => r.enabled);

  // Fetch tracking numbers from DB
  const { data: trackingNumbers } = useQuery({
    queryKey: ["phone-lines", businessId],
    queryFn: () => getPhoneLines(businessId),
    enabled: !!businessId,
  });

  const mainlineNumber = trackingNumbers?.find((t) => t.line_type === "mainline");
  const campaignNumbers = trackingNumbers?.filter((t) => t.line_type !== "mainline" && t.active) ?? [];

  return (
    <div className="rounded-lg border border-border p-5 overflow-x-auto">
      <div className="flex flex-col items-center min-w-[400px]">
        {/* Tracking Numbers (top row - campaign sources from DB) */}
        {campaignNumbers.length > 0 && (
          <>
            <div className="flex items-center gap-3 flex-wrap justify-center mb-1">
              {campaignNumbers.map((tn) => (
                <FlowNode
                  key={tn.id}
                  icon={<Hash size={12} />}
                  label={tn.campaign_name || tn.friendly_name || "Campaign"}
                  sublabel={tn.twilio_number}
                  color="violet"
                />
              ))}
            </div>
            <div className="flex items-center gap-3 justify-center">
              {campaignNumbers.map((tn) => (
                <FlowArrow key={tn.id} />
              ))}
            </div>
          </>
        )}

        {/* Main Line */}
        <FlowNode
          icon={<Phone size={14} />}
          label="Mainline IVR"
          sublabel={mainlineNumber?.twilio_number || "Not configured"}
          color="blue"
          large
        />

        <FlowArrow />

        {/* Department routing branches */}
        {activeRules.length > 0 ? (
          <div className="w-full">
            <div className="flex items-start justify-center gap-4 flex-wrap">
              {activeRules.map((rule: DepartmentRoutingRule, idx: number) => (
                <div key={rule.department_id ?? idx} className="flex flex-col items-center">
                  <FlowNode
                    icon={<PhoneForwarded size={12} />}
                    label={rule.name}
                    sublabel={rule.forward_number || "Uses mainline"}
                    color="emerald"
                  />
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div className="rounded-lg border border-dashed border-border py-4 px-6 text-center">
            <p className="text-sm text-muted-foreground">
              No department routing configured
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Flow Chart Primitives ──

const FLOW_COLORS = {
  violet: {
    bg: "bg-violet-50 dark:bg-violet-900/10",
    border: "border-violet-200 dark:border-violet-800",
    icon: "text-violet-600 dark:text-violet-400",
    label: "text-violet-900 dark:text-violet-100",
  },
  blue: {
    bg: "bg-blue-50 dark:bg-blue-900/10",
    border: "border-blue-200 dark:border-blue-800",
    icon: "text-blue-600 dark:text-blue-400",
    label: "text-blue-900 dark:text-blue-100",
  },
  sky: {
    bg: "bg-sky-50 dark:bg-sky-900/10",
    border: "border-sky-200 dark:border-sky-800",
    icon: "text-sky-600 dark:text-sky-400",
    label: "text-sky-900 dark:text-sky-100",
  },
  emerald: {
    bg: "bg-emerald-50 dark:bg-emerald-900/10",
    border: "border-emerald-200 dark:border-emerald-800",
    icon: "text-emerald-600 dark:text-emerald-400",
    label: "text-emerald-900 dark:text-emerald-100",
  },
};

function FlowNode({
  icon,
  label,
  sublabel,
  color,
  large,
}: {
  icon: React.ReactNode;
  label: string;
  sublabel?: string;
  color: keyof typeof FLOW_COLORS;
  large?: boolean;
}) {
  const c = FLOW_COLORS[color];
  return (
    <div
      className={cn(
        "flex flex-col items-center gap-1 rounded-lg border px-4 py-2.5 text-center",
        c.bg,
        c.border,
        large ? "min-w-[160px]" : "min-w-[110px]",
      )}
    >
      <div className="flex items-center gap-1.5">
        <span className={c.icon}>{icon}</span>
        <span className={cn("text-sm font-semibold", c.label)}>{label}</span>
      </div>
      {sublabel && (
        <span className="text-[10px] text-muted-foreground">{sublabel}</span>
      )}
    </div>
  );
}

function FlowArrow() {
  return (
    <div className="flex flex-col items-center py-1">
      <div className="h-4 w-px bg-border" />
      <div className="h-0 w-0 border-l-[4px] border-r-[4px] border-t-[5px] border-l-transparent border-r-transparent border-t-border" />
    </div>
  );
}

// ── Chat Section ──

function ChatSection({
  businessId,
  employeeId,
  employeeName,
  pendingMessage,
  onPendingConsumed,
}: {
  businessId: string;
  employeeId: string;
  employeeName: string;
  pendingMessage?: string | null;
  onPendingConsumed?: () => void;
}) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const queryClient = useQueryClient();

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
      // Refresh data after chat actions
      queryClient.invalidateQueries({ queryKey: ["twilio-status"] });
      queryClient.invalidateQueries({ queryKey: ["twilio-numbers"] });
      queryClient.invalidateQueries({ queryKey: ["phone-settings"] });
    },
  });

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, mutation.isPending]);

  // Auto-populate from pending message
  useEffect(() => {
    if (pendingMessage && !mutation.isPending) {
      setInput(pendingMessage);
      onPendingConsumed?.();
    }
  }, [pendingMessage]);

  const handleSend = () => {
    const trimmed = input.trim();
    if (!trimmed || mutation.isPending) return;
    setInput("");
    mutation.mutate(trimmed);
  };

  return (
    <div className="flex flex-col">
      {/* Messages */}
      <div ref={scrollRef} className="max-h-96 min-h-[200px] overflow-y-auto space-y-3 mb-4">
        {messages.length === 0 && !mutation.isPending && (
          <div className="flex flex-col items-center justify-center py-12 text-center">
            <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-primary/10">
              <MessageSquare size={20} className="text-primary" />
            </div>
            <p className="text-sm font-medium">Chat with {employeeName}</p>
            <p className="mt-1 max-w-sm text-xs text-muted-foreground">
              Ask about phone setup, Twilio configuration, IVR routing, business hours, or any admin task. {employeeName} can help configure your phone system.
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
                <p className="whitespace-pre-wrap">{msg.content}</p>
              )}
            </div>
          </div>
        ))}

        {mutation.isPending && (
          <div className="flex justify-start">
            <div className="flex items-center gap-2 rounded-lg bg-muted px-4 py-2.5">
              <Loader2 size={14} className="animate-spin text-muted-foreground" />
              <span className="text-xs text-muted-foreground">{employeeName} is thinking...</span>
            </div>
          </div>
        )}
      </div>

      {/* Input */}
      <div className="flex items-center gap-2 border-t border-border pt-4">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleSend()}
          placeholder={`Message ${employeeName}...`}
          disabled={mutation.isPending}
          className="flex-1 rounded-lg border border-border bg-background px-4 py-2.5 text-sm outline-none transition-colors focus:border-primary"
        />
        <button
          onClick={handleSend}
          disabled={!input.trim() || mutation.isPending}
          className={cn(
            "flex h-10 w-10 shrink-0 items-center justify-center rounded-lg transition-colors",
            input.trim() && !mutation.isPending
              ? "bg-primary text-primary-foreground hover:bg-primary/90"
              : "bg-muted text-muted-foreground cursor-not-allowed",
          )}
        >
          <Send size={16} />
        </button>
      </div>

      {mutation.isError && (
        <p className="mt-2 text-xs text-destructive">
          {mutation.error instanceof Error ? mutation.error.message : "Failed to send message"}
        </p>
      )}
    </div>
  );
}


