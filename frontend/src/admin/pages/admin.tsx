import { useState, useRef, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Phone,
  MessageSquare,
  ChevronDown,
  Loader2,
  PhoneForwarded,
  Mic,
  Volume2,
  Pencil,
  Check,
  X,
  Plus,
  Trash2,
  Clock,
  AlertTriangle,
  Hash,
} from "lucide-react";
import { cn } from "@/shared/lib/utils";
import { useAppStore } from "@/shared/stores/app-store";
// APIs
import {
  getPhoneSettings,
  updatePhoneSettings,
  type PhoneSettingsRead,
  type PhoneSettingsUpdate,
  type DepartmentRoutingRule,
} from "@/marketing/api/tracking-routing";
import {
  listACSNumbers,
  searchAvailableNumbers,
  provisionPhoneLine,
  releaseNumber,
  type AvailableNumber,
} from "@/admin/api/acs";

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

  // Phone number action state
  const [editingDeptId, setEditingDeptId] = useState<string | null>(null);
  const [deptNumberDraft, setDeptNumberDraft] = useState("");
  const [confirmDisconnectDeptId, setConfirmDisconnectDeptId] = useState<string | null>(null);
  const [showSmsInfo, setShowSmsInfo] = useState(false);
  const [confirmRemoveId, setConfirmRemoveId] = useState<string | null>(null);
  const [addDialog, setAddDialog] = useState<"mainline" | "tracking" | "department" | null>(null);
  // ACS number search state (mainline + tracking dialogs)
  const [areaCode, setAreaCode] = useState("");
  const [availableNums, setAvailableNums] = useState<AvailableNumber[]>([]);
  const [numSearching, setNumSearching] = useState(false);
  const [numSearchError, setNumSearchError] = useState<string | null>(null);
  const [addCampaign, setAddCampaign] = useState("");

  const queryClient = useQueryClient();

  // Phone settings
  const { data: phoneSettings } = useQuery({
    queryKey: ["phone-settings", bizId],
    queryFn: () => getPhoneSettings(bizId),
    enabled: !!bizId,
    staleTime: 30_000,
  });

  // Tracking numbers (mainline + campaigns) — read directly from Azure ACS
  const { data: trackingNumbers } = useQuery({
    queryKey: ["acs-numbers", bizId],
    queryFn: () => listACSNumbers(bizId),
    enabled: !!bizId,
  });

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

  // General phone settings save — optimistic updates for instant UI
  const settingsMutation = useMutation({
    mutationFn: (payload: PhoneSettingsUpdate) =>
      updatePhoneSettings(bizId, payload),
    onMutate: async (payload) => {
      await queryClient.cancelQueries({ queryKey: ["phone-settings", bizId] });
      const previous = queryClient.getQueryData<PhoneSettingsRead>(["phone-settings", bizId]);
      if (previous) {
        queryClient.setQueryData<PhoneSettingsRead>(["phone-settings", bizId], {
          ...previous,
          ...Object.fromEntries(Object.entries(payload).filter(([, v]) => v !== undefined)),
        } as PhoneSettingsRead);
      }
      return { previous };
    },
    onSuccess: (data) => {
      queryClient.setQueryData<PhoneSettingsRead>(["phone-settings", bizId], data);
    },
    onError: (_err, _payload, context) => {
      if (context?.previous) {
        queryClient.setQueryData(["phone-settings", bizId], context.previous);
      }
    },
  });

  const saveSettings = (patch: PhoneSettingsUpdate) => settingsMutation.mutate(patch);

  // Mutation: provision a new ACS cloud number
  const provisionMutation = useMutation({
    mutationFn: ({ lineType }: { lineType: "mainline" | "tracking" }) =>
      provisionPhoneLine(bizId, areaCode.trim(), addCampaign.trim() || lineType, lineType),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["acs-numbers", bizId] });
      setAddDialog(null);
      setAreaCode("");
      setAvailableNums([]);
      setAddCampaign("");
    },
    onError: () => {
      setNumSearchError("Provisioning failed. ACS may be rate limiting — wait a moment and try again.");
    },
  });

  const releaseMutation = useMutation({
    mutationFn: (phoneNumber: string) => releaseNumber(bizId, phoneNumber),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["acs-numbers", bizId] });
      setConfirmRemoveId(null);
    },
  });

  const handleSearchNumbers = async () => {
    if (areaCode.trim().length !== 3) return;
    setNumSearching(true);
    setNumSearchError(null);
    setAvailableNums([]);
    try {
      const nums = await searchAvailableNumbers(areaCode.trim());
      if (nums.length === 0) setNumSearchError("No numbers available in that area code. Try another.");
      else setAvailableNums(nums);
    } catch {
      setNumSearchError("Search failed. Please try again.");
    } finally {
      setNumSearching(false);
    }
  };

  // ── Section: Numbers ──
  const allPhoneLines = trackingNumbers ?? [];

  const numbersContent = (
    <div className="space-y-6">
      {/* ─ Mainline ─ */}
      <div>
        <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-2">Mainline</p>
        {mainlineNumber ? (
          <div className="rounded-lg border border-border bg-card p-4 flex items-start justify-between">
            <div>
              <p className="font-mono text-base">{mainlineNumber.phone_number}</p>
              <span className="mt-1 inline-block rounded-full bg-primary/10 text-primary px-2 py-0.5 text-[10px] font-medium">Mainline</span>
            </div>
            <button
              type="button"
              onClick={() => setConfirmRemoveId(mainlineNumber.id)}
              className="rounded p-1.5 text-muted-foreground hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 transition-all"
              title="Remove"
            >
              <Trash2 size={14} />
            </button>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => { setAddDialog("mainline"); setAreaCode(""); setAvailableNums([]); setNumSearchError(null); }}
            className="w-full rounded-lg border border-dashed border-border p-6 flex flex-col items-center gap-2 text-muted-foreground hover:bg-muted/40 hover:border-primary/30 transition-colors group"
          >
            <Plus size={20} className="group-hover:text-primary transition-colors" />
            <span className="text-sm font-medium">Add Mainline Number</span>
            <span className="text-xs text-center max-w-[240px] leading-relaxed">Your main business number — all inbound calls route through here via AI IVR.</span>
          </button>
        )}
      </div>

      {/* ─ Tracking Numbers ─ */}
      <div className={cn(!mainlineNumber && "pointer-events-none opacity-40")}>
        <div className="flex items-center justify-between mb-2">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Tracking Numbers</p>
          {mainlineNumber && (
            <button
              type="button"
              disabled={allPhoneLines.length >= 5}
              onClick={() => { setAddDialog("tracking"); setAreaCode(""); setAvailableNums([]); setNumSearchError(null); setAddCampaign(""); }}
              title={allPhoneLines.length >= 5 ? "5/5 cloud numbers used" : undefined}
              className="flex items-center gap-1 text-xs text-primary hover:text-primary/80 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              <Plus size={12} /> Add
            </button>
          )}
        </div>
        {campaignNumbers.length > 0 ? (
          <div className="space-y-2">
            {campaignNumbers.map((line) => (
              <div key={line.id} className="rounded-lg border border-border bg-card p-3 flex items-center justify-between">
                <div>
                  <p className="font-mono text-sm">{line.phone_number}</p>
                  <p className="text-[10px] text-muted-foreground mt-0.5">{line.campaign_name || "Tracking"}</p>
                </div>
                <button
                  type="button"
                  onClick={() => setConfirmRemoveId(line.id)}
                  className="rounded p-1.5 text-muted-foreground hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 transition-all"
                >
                  <Trash2 size={13} />
                </button>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-xs text-muted-foreground py-1">
            {mainlineNumber ? "No tracking numbers yet — add one to attribute calls to a marketing campaign." : "Add a mainline number first."}
          </p>
        )}
        <p className="text-[10px] text-muted-foreground mt-2 tabular-nums">{allPhoneLines.length}/5 cloud numbers used</p>
      </div>

      {/* ─ Remove confirm modal ─ */}
      {confirmRemoveId && (() => {
        const line = allPhoneLines.find((l) => l.id === confirmRemoveId);
        if (!line) return null;
        return (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={() => setConfirmRemoveId(null)}>
            <div className="w-full max-w-sm rounded-xl border border-border bg-background p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
              <p className="font-semibold mb-1">Remove {line.line_type === "mainline" ? "mainline" : "tracking"} number?</p>
              <p className="text-sm text-muted-foreground mb-4 font-mono">{line.phone_number}</p>
              <div className="flex justify-end gap-2">
                <button type="button" onClick={() => setConfirmRemoveId(null)} className="rounded px-3 py-1.5 text-xs text-muted-foreground hover:bg-muted transition-colors">Cancel</button>
                <button
                  type="button"
                  disabled={releaseMutation.isPending}
                  onClick={() => releaseMutation.mutate(line.phone_number)}
                  className="rounded bg-red-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-600 disabled:opacity-50 transition-colors"
                >
                  {releaseMutation.isPending ? "Removing…" : "Remove"}
                </button>
              </div>
            </div>
          </div>
        );
      })()}

      {/* ─ Add Dialogs ─ */}
      {addDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={() => setAddDialog(null)}>
          <div className="w-full max-w-md rounded-xl border border-border bg-background p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
            {(addDialog === "mainline" || addDialog === "tracking") && (
              <>
                <div className="mb-5">
                  <h3 className="font-semibold">
                    {addDialog === "mainline" ? "Add Mainline Number" : "Add Tracking Number"}
                  </h3>
                  <p className="text-xs text-muted-foreground mt-1.5">
                    {addDialog === "mainline"
                      ? "Your main business number. All inbound calls come in here and are routed by the AI IVR to the right department."
                      : "Assign a unique number to a marketing campaign (Google Ads, billboards, etc.) to track which source drives calls."}
                  </p>
                </div>
                <div className="space-y-4">
                  {addDialog === "tracking" && (
                    <div>
                      <label className="text-xs font-medium text-muted-foreground">Campaign Name</label>
                      <input
                        type="text"
                        value={addCampaign}
                        onChange={(e) => setAddCampaign(e.target.value)}
                        placeholder="e.g. Google Ads, Billboard, Yelp"
                        autoFocus
                        className="mt-1.5 w-full rounded border border-border bg-background px-2.5 py-1.5 text-sm outline-none focus:border-primary transition-colors"
                      />
                    </div>
                  )}
                  <div>
                    <label className="text-xs font-medium text-muted-foreground">Area Code</label>
                    <div className="mt-1.5 flex gap-2">
                      <input
                        type="text"
                        value={areaCode}
                        onChange={(e) => {
                          const v = e.target.value.replace(/\D/g, "").slice(0, 3);
                          setAreaCode(v);
                          setAvailableNums([]);
                          setNumSearchError(null);
                        }}
                        placeholder="e.g. 214"
                        maxLength={3}
                        autoFocus={addDialog === "mainline"}
                        onKeyDown={(e) => { if (e.key === "Enter" && areaCode.length === 3) handleSearchNumbers(); }}
                        className="w-28 rounded border border-border bg-background px-2.5 py-1.5 text-sm font-mono outline-none focus:border-primary transition-colors"
                      />
                      <button
                        type="button"
                        onClick={handleSearchNumbers}
                        disabled={areaCode.length !== 3 || numSearching}
                        className="rounded-md border border-border px-3 py-1.5 text-xs font-medium text-muted-foreground hover:bg-muted disabled:opacity-40 transition-colors"
                      >
                        {numSearching ? <Loader2 size={13} className="animate-spin" /> : "Search"}
                      </button>
                    </div>
                  </div>
                  {numSearchError && (
                    <div className="flex items-start gap-2 rounded-md border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-950/30 px-3 py-2.5">
                      <AlertTriangle size={13} className="mt-0.5 shrink-0 text-red-500" />
                      <p className="text-xs text-red-700 dark:text-red-400">{numSearchError}</p>
                    </div>
                  )}
                  {availableNums.length > 0 && (
                    <div className="rounded-md border border-border">
                      {availableNums.map((n) => (
                        <div key={n.phone_number} className="flex items-center justify-between px-3 py-2.5">
                          <span className="font-mono text-sm">{n.phone_number}</span>
                          <div className="flex items-center gap-2">
                            <button
                              type="button"
                              onClick={handleSearchNumbers}
                              disabled={numSearching}
                              className="text-[10px] text-muted-foreground hover:text-foreground underline underline-offset-2 disabled:opacity-40 transition-colors"
                            >
                              {numSearching ? "Searching…" : "Try another"}
                            </button>
                            <span className="text-[10px] text-muted-foreground">${n.cost_monthly}/mo</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
                <div className="mt-5 flex items-center justify-end gap-2">
                  <button type="button" onClick={() => setAddDialog(null)} className="rounded px-3 py-1.5 text-xs text-muted-foreground hover:bg-muted transition-colors">Cancel</button>
                  <button
                    type="button"
                    disabled={availableNums.length === 0 || provisionMutation.isPending}
                    onClick={() => provisionMutation.mutate({ lineType: addDialog })}
                    className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-40 transition-colors"
                  >
                    {provisionMutation.isPending
                      ? "Provisioning…"
                      : addDialog === "mainline" ? "Get Mainline Number" : "Get Tracking Number"}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );

  // ── Section: IVR ──
  const defaultGreeting = `Hi, you've reached ${business?.name ?? "us"}. Please state your name and reason for calling so we can best route your call.`;
  const defaultHoldMessage = "Thank you, please hold.";

  const ivrContent = (
    <div>
      <div className="grid gap-6 sm:grid-cols-2 items-start">
        {/* Greeting & Voice */}
        <SettingsCard icon={<Volume2 size={14} />} title="Greeting & Voice">
          <div className="space-y-4">
            <EditableText
              label="Greeting"
              value={phoneSettings?.greeting_text ?? null}
              placeholder={defaultGreeting}
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
          <div className="space-y-3">
            <EditableText
              label="Hold Message"
              value={phoneSettings?.hold_message ?? null}
              placeholder={defaultHoldMessage}
              multiline
              onSave={(v) => saveSettings({ hold_message: v })}
            />
            <p className="text-[10px] text-muted-foreground">
              Plays while the caller waits. After this plays, an SMS is sent to the department's forwarding number with the caller's name and reason.
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
  );

  // ── Section: Routing ──
  const routingContent = (
    <div className="space-y-5">
      {!mainlineNumber && (
        <div className="flex items-center gap-3 rounded-lg border border-dashed border-border p-4">
          <Phone size={18} className="shrink-0 text-muted-foreground/50" />
          <p className="text-sm text-muted-foreground">
            Add a mainline number in <strong className="text-foreground">Numbers</strong> to enable call routing.
          </p>
        </div>
      )}

      <div className={cn("grid gap-3 sm:grid-cols-2", !mainlineNumber && "pointer-events-none opacity-40")}>
        {deptConfig.map((dept) => {
          const isEditingThis = editingDeptId === dept.department_id;
          const isConfirmingDisconnect = confirmDisconnectDeptId === dept.department_id;
          return (
            <div key={dept.department_id ?? dept.name} className="rounded-lg border border-border bg-card p-4 space-y-3">
              <div className="flex items-center justify-between">
                <p className="text-sm font-semibold">{dept.name}</p>
                {dept.forward_number && (
                  <button
                    type="button"
                    onClick={() => toggleDept(dept.department_id)}
                    title={dept.enabled ? "Disable routing" : "Enable routing"}
                    className={cn(
                      "relative inline-flex h-5 w-9 shrink-0 rounded-full border-2 border-transparent transition-colors cursor-pointer",
                      dept.enabled ? "bg-primary" : "bg-muted-foreground/30",
                    )}
                  >
                    <span className={cn("pointer-events-none inline-block h-4 w-4 rounded-full bg-white shadow-sm transition-transform", dept.enabled ? "translate-x-4" : "translate-x-0")} />
                  </button>
                )}
              </div>

              {isEditingThis ? (
                <div className="flex items-center gap-1.5">
                  <input
                    type="tel"
                    value={deptNumberDraft}
                    onChange={(e) => setDeptNumberDraft(e.target.value)}
                    placeholder="Your existing number"
                    className="flex-1 rounded border border-border bg-background px-2.5 py-1.5 text-sm outline-none focus:border-primary transition-colors font-mono"
                    autoFocus
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && deptNumberDraft.trim()) saveDeptForwardNumber(dept.department_id, deptNumberDraft.trim());
                      if (e.key === "Escape") setEditingDeptId(null);
                    }}
                  />
                  <button type="button" onClick={() => { if (deptNumberDraft.trim()) saveDeptForwardNumber(dept.department_id, deptNumberDraft.trim()); }} className="rounded p-1.5 text-primary hover:bg-primary/10 transition-colors"><Check size={14} /></button>
                  <button type="button" onClick={() => setEditingDeptId(null)} className="rounded p-1.5 text-muted-foreground hover:bg-muted transition-colors"><X size={14} /></button>
                </div>
              ) : dept.forward_number ? (
                <div className="flex items-center gap-2">
                  <span className="font-mono text-sm text-muted-foreground flex-1 truncate">{dept.forward_number}</span>
                  <button type="button" onClick={() => { setEditingDeptId(dept.department_id); setDeptNumberDraft(dept.forward_number ?? ""); }} className="rounded p-1 text-muted-foreground hover:bg-muted transition-colors"><Pencil size={12} /></button>
                </div>
              ) : (
                <button
                  type="button"
                  onClick={() => { setEditingDeptId(dept.department_id); setDeptNumberDraft(""); }}
                  className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-primary transition-colors"
                >
                  <Plus size={11} /> Add forwarding number
                </button>
              )}

              {dept.forward_number && dept.enabled && (
                <div className="flex items-center justify-between border-t border-border pt-2.5">
                  <span className="text-xs text-muted-foreground">SMS notifications</span>
                  <button
                    type="button"
                    onClick={() => { if (!dept.sms_enabled) { setShowSmsInfo(true); return; } toggleDeptSms(dept.department_id); }}
                    className={cn(
                      "relative inline-flex h-5 w-9 shrink-0 rounded-full border-2 border-transparent transition-colors cursor-pointer",
                      dept.sms_enabled ? "bg-primary" : "bg-muted-foreground/30",
                    )}
                  >
                    <span className={cn("pointer-events-none inline-block h-4 w-4 rounded-full bg-white shadow-sm transition-transform", dept.sms_enabled ? "translate-x-4" : "translate-x-0")} />
                  </button>
                </div>
              )}

              {isConfirmingDisconnect ? (
                <div className="flex items-center gap-2 rounded-md bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-900 px-3 py-2">
                  <p className="text-xs text-red-700 dark:text-red-400 flex-1">Remove forwarding number?</p>
                  <button type="button" onClick={() => { saveDeptForwardNumber(dept.department_id, ""); setConfirmDisconnectDeptId(null); }} className="rounded bg-red-500 px-2 py-0.5 text-[10px] font-medium text-white hover:bg-red-600 transition-colors">Remove</button>
                  <button type="button" onClick={() => setConfirmDisconnectDeptId(null)} className="text-[10px] text-muted-foreground hover:text-foreground">Cancel</button>
                </div>
              ) : dept.forward_number ? (
                <button
                  type="button"
                  onClick={() => setConfirmDisconnectDeptId(dept.department_id)}
                  className="flex items-center gap-1 text-[10px] text-red-500/70 hover:text-red-500 transition-colors"
                >
                  <Trash2 size={10} /> Remove number
                </button>
              ) : null}
            </div>
          );
        })}
      </div>

      {mainlineNumber && <CallFlowSection phoneSettings={phoneSettings ?? null} businessId={bizId} />}

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
                  US carriers require A2P (Application-to-Person) registration for business SMS. Azure Communication Services handles this registration on your behalf. Contact your account manager to initiate.
                </p>
                <p className="mt-1.5">Approval typically takes <span className="font-medium text-foreground">1–7 business days</span>.</p>
              </div>
              <div className="flex items-center gap-2">
                <div className="h-2 w-2 rounded-full shrink-0 bg-amber-500" />
                <span className="text-[11px]">Contact your account manager to complete A2P registration for ACS SMS.</span>
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
    </div>
  );

  return (
    <div className="space-y-10">
      {/* ── Phone Numbers ── */}
      <section>
        <div className="flex items-center gap-3 mb-5">
          <p className="text-sm font-semibold">Phone Numbers</p>
          <div className="flex-1 h-px bg-border" />
        </div>
        {numbersContent}
      </section>

      {/* ── Department Routing ── */}
      <section>
        <div className="flex items-center gap-3 mb-5">
          <p className="text-sm font-semibold">Department Routing</p>
          <div className="flex-1 h-px bg-border" />
        </div>
        {routingContent}
      </section>

      {/* ── IVR Settings ── */}
      <section className={cn(!mainlineNumber && "pointer-events-none opacity-40")}>
        <div className="flex items-center gap-3 mb-5">
          <p className="text-sm font-semibold">IVR Settings</p>
          {!mainlineNumber && (
            <span className="text-xs text-muted-foreground">— add a mainline number first</span>
          )}
          <div className="flex-1 h-px bg-border" />
        </div>
        {ivrContent}
      </section>
    </div>
  );
}

// ── Time Picker (hour · minute · AM/PM) ──

function TimePicker({
  value,
  onChange,
}: {
  value: string | null;
  onChange: (val: string | null) => void;
}) {
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

  const { data: trackingNumbers } = useQuery({
    queryKey: ["acs-numbers", businessId],
    queryFn: () => listACSNumbers(businessId),
    enabled: !!businessId,
  });

  const mainlineNumber = trackingNumbers?.find((t) => t.line_type === "mainline");
  const campaignNumbers = trackingNumbers?.filter((t) => t.line_type !== "mainline" && t.active) ?? [];

  if (!mainlineNumber) {
    return (
      <div className="rounded-lg border border-dashed border-border py-8 text-center">
        <Phone size={24} className="mx-auto mb-2 text-muted-foreground/40" />
        <p className="text-sm text-muted-foreground">No mainline number configured</p>
        <p className="text-xs text-muted-foreground/70 mt-1">Add a mainline number in the Numbers tab to see the call flow</p>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-border p-5 overflow-x-auto">
      <div className="flex flex-col items-center min-w-[400px]">
        {campaignNumbers.length > 0 && (
          <>
            <div className="flex items-center gap-3 flex-wrap justify-center mb-1">
              {campaignNumbers.map((tn) => (
                <FlowNode
                  key={tn.id}
                  icon={<Hash size={12} />}
                  label={tn.campaign_name || tn.friendly_name || "Campaign"}
                  sublabel={tn.phone_number}
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

        <FlowNode
          icon={<Phone size={14} />}
          label="Mainline IVR"
          sublabel={mainlineNumber.phone_number}
          color="blue"
          large
        />

        <FlowArrow />

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
