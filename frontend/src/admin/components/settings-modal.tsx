/**
 * Settings modal for Tracking & Routing — mainline configuration,
 * call flow (greeting + hold message), voice, and department routing.
 *
 * Department routing forwards calls to personal phone numbers per department.
 * AI listens to the caller's reason and routes to the matching department's number.
 */
import { useState, useEffect, useCallback } from "react";
import { X, Plus, Trash2, Loader2, CheckCircle2, Phone } from "lucide-react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/shared/components/ui/button";
import { Card, CardContent } from "@/shared/components/ui/card";
import { Input } from "@/shared/components/ui/input";
import {
  getPhoneSettings,
  updatePhoneSettings,
  testGreetingCall,
  type PhoneSettingsUpdate,
  type DepartmentRoutingRule,
} from "@/marketing/api/tracking-routing";
import { listDepartments } from "@/shared/api/organization";
import type { Department } from "@/shared/types/organization";

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  businessId: string;
  mainlineNumber?: string;
}

const VOICE_OPTIONS = [
  { value: "Google.en-US-Chirp3-HD-Aoede", label: "Aoede — Female" },
  { value: "Google.en-US-Chirp3-HD-Leda", label: "Leda — Female" },
  { value: "Google.en-US-Chirp3-HD-Charon", label: "Charon — Male" },
  { value: "Google.en-US-Chirp3-HD-Puck", label: "Puck — Male" },
];

/** Local state for a department routing row */
interface DeptRoutingRow {
  name: string;
  department_id: string | null;
  forward_number: string;
  enabled: boolean;
}

export function SettingsModal({ isOpen, onClose, businessId, mainlineNumber }: SettingsModalProps) {
  const queryClient = useQueryClient();
  const [greeting, setGreeting] = useState("");
  const [holdMessage, setHoldMessage] = useState("");
  const [voice, setVoice] = useState("Google.en-US-Chirp3-HD-Aoede");
  const [recording, setRecording] = useState(true);
  const [transcription, setTranscription] = useState(false);
  const [defaultForwardNumber, setDefaultForwardNumber] = useState("");
  const [ringTimeout, setRingTimeout] = useState(30);
  const [deptRows, setDeptRows] = useState<DeptRoutingRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  // Fetch phone settings, departments, and tracking numbers
  const settings = useQuery({
    queryKey: ["phone-settings", businessId],
    queryFn: () => getPhoneSettings(businessId),
    enabled: isOpen && !!businessId,
  });

  const departmentsQuery = useQuery({
    queryKey: ["departments", businessId],
    queryFn: () => listDepartments(businessId),
    enabled: isOpen && !!businessId,
  });

  const orgDepartments: Department[] = departmentsQuery.data || [];

  const updateMutation = useMutation({
    mutationFn: (payload: PhoneSettingsUpdate) => updatePhoneSettings(businessId, payload),
    onSuccess: () => {
      setSuccess(true);
      setTimeout(() => setSuccess(false), 3000);
      settings.refetch();
      queryClient.invalidateQueries({ queryKey: ["phone-settings", businessId] });
    },
    onError: (err: unknown) => {
      const message = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || "Failed to save";
      setError(message);
    },
  });

  // Hydrate local state from fetched data
  useEffect(() => {
    if (settings.data) {
      setGreeting(settings.data.greeting_text || "");
      setHoldMessage(settings.data.hold_message || "Thank you, please hold while I connect your call. This call may be recorded for quality purposes.");
      setVoice(settings.data.voice_name || "Google.en-US-Chirp3-HD-Aoede");
      setRecording(settings.data.recording_enabled ?? true);
      setTranscription(settings.data.transcription_enabled ?? false);
      setDefaultForwardNumber(settings.data.default_forward_number || "");
      setRingTimeout(settings.data.ring_timeout_s || 30);

      // Build department routing rows from config
      const config: DepartmentRoutingRule[] = settings.data.departments_config || [];
      const rows: DeptRoutingRow[] = config.map((rule) => ({
        name: rule.name,
        department_id: rule.department_id,
        forward_number: rule.forward_number || "",
        enabled: rule.enabled,
      }));
      setDeptRows(rows);
    }
  }, [settings.data]);

  const handleSave = useCallback(async () => {
    setError(null);

    // 1. Save phone settings with department routing config
    const deptConfig: DepartmentRoutingRule[] = deptRows
      .filter((row) => row.department_id)
      .map((row) => ({
        name: row.name,
        department_id: row.department_id!,
        forward_number: row.forward_number || null,
        enabled: row.enabled,
        sms_enabled: false,
        whatsapp_enabled: false,
        whatsapp_sender_sid: null,
        whatsapp_sender_status: "none",
      }));

    await updateMutation.mutateAsync({
      greeting_text: greeting,
      hold_message: holdMessage,
      voice_name: voice,
      recording_enabled: true,
      transcription_enabled: true,
      default_forward_number: defaultForwardNumber || undefined,
      ring_timeout_s: ringTimeout,
      departments_config: deptConfig,
    });

  }, [greeting, holdMessage, voice, recording, transcription, defaultForwardNumber, ringTimeout, deptRows, updateMutation, businessId]);

  const addDepartment = useCallback(() => {
    setDeptRows((prev) => [
      ...prev,
      { name: "", department_id: null, forward_number: "", enabled: true },
    ]);
  }, []);

  const updateRow = useCallback((idx: number, updated: DeptRoutingRow) => {
    setDeptRows((prev) => {
      const next = [...prev];
      next[idx] = updated;
      return next;
    });
  }, []);

  const removeRow = useCallback((idx: number) => {
    setDeptRows((prev) => prev.filter((_, i) => i !== idx));
  }, []);

  // When user picks a department from the dropdown, auto-fill name + department_id
  const handleDeptSelect = useCallback((idx: number, deptId: string) => {
    const dept = orgDepartments.find(d => d.id === deptId);
    if (!dept) return;
    setDeptRows((prev) => {
      const next = [...prev];
      next[idx] = { ...next[idx], name: dept.name, department_id: dept.id };
      return next;
    });
  }, [orgDepartments]);

  // ── Test call ──
  const [testPhone, setTestPhone] = useState("");
  const [testCalling, setTestCalling] = useState(false);
  const [testResult, setTestResult] = useState<string | null>(null);

  const handleTestCall = useCallback(async () => {
    if (!testPhone.trim()) return;
    setTestCalling(true);
    setTestResult(null);
    try {
      // Normalize to E.164: strip non-digits, prepend +1 if needed
      let digits = testPhone.trim().replace(/\D/g, "");
      if (digits.length === 10) digits = "1" + digits;
      const e164 = "+" + digits;
      const res = await testGreetingCall(businessId, e164);
      if (res.status === "busy") {
        setTestResult(res.message || "Your phone returned a busy signal. Try adding the mainline number to your contacts or check your carrier's spam filter.");
      } else if (res.status === "failed" || res.status === "no-answer" || res.status === "canceled") {
        setTestResult(res.message || `Call ${res.status}. Check that your phone is on and can receive calls.`);
      } else {
        setTestResult("Calling you now — pick up to hear the full call flow!");
      }
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || "Test call failed";
      setTestResult(msg);
    } finally {
      setTestCalling(false);
    }
  }, [businessId, testPhone]);

  if (!isOpen) return null;

  // Department IDs already used in routing rows (to prevent duplicates)
  const usedDeptIds = new Set(deptRows.map(r => r.department_id).filter(Boolean));

  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
      <div className="w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-xl border bg-background shadow-lg">
        {/* Header */}
        <div className="sticky top-0 z-10 flex items-center justify-between border-b bg-background px-6 py-4">
          <div>
            <h2 className="text-lg font-semibold">Mainline Settings</h2>
            {mainlineNumber && (
              <p className="text-sm text-muted-foreground font-mono">{mainlineNumber}</p>
            )}
          </div>
          <Button variant="ghost" size="sm" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>

        <div className="space-y-6 p-6">
          {/* Status messages */}
          {error && (
            <div className="rounded-lg bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800 p-3 text-sm text-red-700 dark:text-red-300">
              {error}
            </div>
          )}
          {success && (
            <div className="flex items-center gap-2 rounded-lg bg-emerald-50 dark:bg-emerald-950 border border-emerald-200 dark:border-emerald-800 p-3 text-sm text-emerald-700 dark:text-emerald-300">
              <CheckCircle2 className="h-4 w-4" /> Settings saved
            </div>
          )}

          {/* Section 1: Call Flow */}
          <section className="space-y-3">
            <h3 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
              Call Flow
            </h3>

            {/* Step 1: Greeting */}
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground">
                <span className="inline-flex items-center justify-center w-4 h-4 rounded-full bg-primary text-primary-foreground text-[9px] font-bold mr-1.5">1</span>
                Greeting
              </label>
              <textarea
                value={greeting}
                onChange={(e) => setGreeting(e.target.value)}
                placeholder="Thank you for calling {company_name}. May I get your name and reason for calling so I can best route your call?"
                rows={2}
                className="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              />
              <p className="text-[10px] text-muted-foreground">
                What callers hear first. Use {"{company_name}"} for your business name.
              </p>
            </div>

            {/* Caller speaks indicator */}
            <div className="flex items-center gap-2 text-[10px] text-muted-foreground px-1">
              <div className="h-px flex-1 bg-border" />
              <span className="italic">Caller states their name & reason</span>
              <div className="h-px flex-1 bg-border" />
            </div>

            {/* Step 2: Hold / Routing Message */}
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground">
                <span className="inline-flex items-center justify-center w-4 h-4 rounded-full bg-primary text-primary-foreground text-[9px] font-bold mr-1.5">2</span>
                Hold Message
              </label>
              <textarea
                value={holdMessage}
                onChange={(e) => setHoldMessage(e.target.value)}
                placeholder="Thank you, please hold while I connect your call. This call may be recorded for quality purposes."
                rows={2}
                className="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              />
              <p className="text-[10px] text-muted-foreground">
                Plays while the caller is being connected. Include recording disclosure if calls are recorded.
              </p>
            </div>

            {/* Connected indicator */}
            <div className="flex items-center gap-2 text-[10px] text-muted-foreground px-1">
              <div className="h-px flex-1 bg-border" />
              <span className="italic">Call connects to you</span>
              <div className="h-px flex-1 bg-border" />
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground">Voice</label>
              <select
                value={voice}
                onChange={(e) => setVoice(e.target.value)}
                className="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              >
                {VOICE_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>

            {/* Test Call */}
            <div className="rounded-lg border bg-muted/30 p-3 space-y-2">
              <label className="text-xs font-medium text-muted-foreground">
                Test Call Flow
              </label>
              <p className="text-[10px] text-muted-foreground">
                Hear the full caller experience: greeting → pause → hold message.
              </p>
              <div className="flex gap-2">
                <Input
                  value={testPhone}
                  onChange={(e) => setTestPhone(e.target.value)}
                  placeholder="+1 (940) 555-1234"
                  className="text-sm h-8 flex-1 font-mono"
                />
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleTestCall}
                  disabled={testCalling || !testPhone.trim()}
                  className="h-8 whitespace-nowrap"
                >
                  {testCalling ? (
                    <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Phone className="mr-1.5 h-3.5 w-3.5" />
                  )}
                  Test Call
                </Button>
              </div>
              {testResult && (
                <p className={`text-xs ${testResult.includes("Calling you now") ? "text-emerald-600" : "text-amber-600"}`}>
                  {testResult}
                </p>
              )}
            </div>
          </section>

          <hr />

          {/* Section 3: Forwarding Rules */}
          <section className="space-y-3">
            <h3 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
              Forwarding Rules
            </h3>
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground">
                Default Forward Number
              </label>
              <Input
                value={defaultForwardNumber}
                onChange={(e) => setDefaultForwardNumber(e.target.value)}
                placeholder="+1 (940) 337-6016"
                className="text-sm font-mono"
              />
              <p className="text-[10px] text-muted-foreground">
                Your personal phone number. All calls forward here unless department routing overrides it.
                {!defaultForwardNumber && (
                  <span className="text-amber-600 font-medium"> Required — calls will hang up without a forward number.</span>
                )}
              </p>
            </div>
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground">
                Ring Timeout (seconds)
              </label>
              <Input
                type="number"
                min={5}
                max={60}
                value={ringTimeout}
                onChange={(e) => setRingTimeout(parseInt(e.target.value) || 30)}
                className="w-32"
              />
              <p className="text-[10px] text-muted-foreground">
                How long to ring before the call ends (5-60s).
              </p>
            </div>
          </section>

          <hr />

          {/* Section 5: Department Routing */}
          <section className="space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
                Department Routing
              </h3>
              <Button variant="outline" size="sm" onClick={addDepartment}>
                <Plus className="mr-1 h-3.5 w-3.5" /> Add
              </Button>
            </div>
            <p className="text-[10px] text-muted-foreground">
              Assign a tracking number to each department. AI listens to the caller's reason and intelligently routes to the right department.
            </p>

            <div className="space-y-3">
              {deptRows.map((row, idx) => (
                <Card key={idx} className="bg-muted/30">
                  <CardContent className="space-y-3 pt-4 pb-3">
                    <div className="grid grid-cols-2 gap-3">
                      <div className="space-y-1">
                        <label className="text-[10px] font-medium text-muted-foreground">
                          Department
                        </label>
                        <select
                          value={row.department_id || ""}
                          onChange={(e) => handleDeptSelect(idx, e.target.value)}
                          className="w-full rounded-md border bg-background px-3 py-1.5 text-sm h-8 focus:outline-none focus:ring-2 focus:ring-primary"
                        >
                          <option value="">Select department...</option>
                          {orgDepartments
                            .filter(d => d.id === row.department_id || !usedDeptIds.has(d.id))
                            .map((d) => (
                              <option key={d.id} value={d.id}>{d.name}</option>
                            ))}
                        </select>
                      </div>
                      <div className="space-y-1">
                        <label className="text-[10px] font-medium text-muted-foreground">
                          Forward To
                        </label>
                        <Input
                          value={row.forward_number}
                          onChange={(e) => updateRow(idx, { ...row, forward_number: e.target.value })}
                          placeholder="(940) 337-6016"
                          className="text-sm h-8 font-mono"
                        />
                      </div>
                    </div>
                    <div className="flex items-center justify-between">
                      <label className="flex items-center gap-2 cursor-pointer text-xs">
                        <input
                          type="checkbox"
                          checked={row.enabled}
                          onChange={(e) => updateRow(idx, { ...row, enabled: e.target.checked })}
                          className="h-3.5 w-3.5 rounded border accent-primary"
                        />
                        Enabled
                      </label>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => removeRow(idx)}
                        className="text-red-500 hover:text-red-600 h-7 px-2"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              ))}
              {deptRows.length === 0 && (
                <p className="text-xs text-muted-foreground italic py-2">
                  No departments configured. Calls will forward to your default number.
                </p>
              )}
            </div>
          </section>

          {/* Save / Cancel */}
          <div className="flex gap-2 pt-4 border-t">
            <Button variant="outline" onClick={onClose} disabled={updateMutation.isPending}>
              Cancel
            </Button>
            <Button onClick={handleSave} disabled={updateMutation.isPending || settings.isLoading}>
              {updateMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Save Settings
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
