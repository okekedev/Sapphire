import { useState, useRef, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  PhoneForwarded,
  Play,
  Pause,
  Settings,
  ArrowRight,
  Phone,
  Loader2,
  Plus,
  X,
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  Eye,
  EyeOff,
  UserPlus,
  ShieldAlert,
  MoreHorizontal,
  ChevronDown,
} from "lucide-react";
import { Card, CardContent } from "@/shared/components/ui/card";
import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { PageHeader } from "@/shared/components/page-header";
import { useAppStore } from "@/shared/stores/app-store";
import {
  listCalls,
  dispositionCall,
  getDepartmentSummary,
  getPhoneSettings,
} from "@/marketing/api/tracking-routing";
import { listACSNumbers, provisionPhoneLine } from "@/admin/api/acs";
import { SettingsModal } from "@/admin/components/settings-modal";

// ── Helpers ──

function formatDuration(seconds: number | null): string {
  if (!seconds) return "—";
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const diff = now.getTime() - d.getTime();
  if (diff < 3600_000) return `${Math.floor(diff / 60_000)}m ago`;
  if (diff < 86400_000) return `${Math.floor(diff / 3600_000)}h ago`;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

const STATUS_STYLES: Record<string, { dot: string; label: string }> = {
  completed: { dot: "bg-emerald-500", label: "Completed" },
  followup: { dot: "bg-amber-500", label: "Follow-Up" },
  dropped: { dot: "bg-gray-400", label: "Dropped" },
};

const CAMPAIGN_COLORS: Record<string, string> = {
  website: "bg-blue-50 text-blue-700 dark:bg-blue-950 dark:text-blue-300",
  google_ads: "bg-orange-50 text-orange-700 dark:bg-orange-950 dark:text-orange-300",
  facebook_ads: "bg-purple-50 text-purple-700 dark:bg-purple-950 dark:text-purple-300",
  referral: "bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300",
  direct_mail: "bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
};

function getCampaignColor(channel: string | null, campaign: string | null): string {
  if (channel && CAMPAIGN_COLORS[channel]) return CAMPAIGN_COLORS[channel];
  const name = (campaign || "").toLowerCase();
  if (name.includes("website") || name.includes("web")) return CAMPAIGN_COLORS.website;
  if (name.includes("google")) return CAMPAIGN_COLORS.google_ads;
  if (name.includes("facebook") || name.includes("fb")) return CAMPAIGN_COLORS.facebook_ads;
  if (name.includes("referral")) return CAMPAIGN_COLORS.referral;
  if (name.includes("mail")) return CAMPAIGN_COLORS.direct_mail;
  return "bg-gray-50 text-gray-700 dark:bg-gray-800 dark:text-gray-300";
}

const DEPT_COLORS: Record<string, string> = {
  Sales: "bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300",
  Operations: "bg-blue-50 text-blue-700 dark:bg-blue-950 dark:text-blue-300",
  Finance: "bg-purple-50 text-purple-700 dark:bg-purple-950 dark:text-purple-300",
  Marketing: "bg-cyan-50 text-cyan-700 dark:bg-cyan-950 dark:text-cyan-300",
  Administration: "bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
  IT: "bg-violet-50 text-violet-700 dark:bg-violet-950 dark:text-violet-300",
};

function getDeptColor(dept: string): string {
  return DEPT_COLORS[dept] || "bg-gray-50 text-gray-700 dark:bg-gray-800 dark:text-gray-300";
}

const CHANNEL_ICONS: Record<string, string> = {
  google_ads: "📢",
  facebook_ads: "📱",
  referral: "🤝",
  direct_mail: "📬",
};

// ── Sort Header ──

function SortHeader({
  label,
  column,
  current,
  order,
  onSort,
}: {
  label: string;
  column: string;
  current: string;
  order: "asc" | "desc";
  onSort: (col: string) => void;
}) {
  const active = current === column;
  return (
    <th
      className="px-3 py-2 text-left cursor-pointer select-none hover:text-foreground transition"
      onClick={() => onSort(column)}
    >
      <span className="inline-flex items-center gap-1">
        {label}
        {active ? (
          order === "asc" ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />
        ) : (
          <ArrowUpDown className="h-3 w-3 opacity-30" />
        )}
      </span>
    </th>
  );
}

// ── Audio Player ──

function AudioPlayButton({ url }: { url: string | null }) {
  const [playing, setPlaying] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  if (!url) return <span className="text-muted-foreground">—</span>;

  const toggle = () => {
    if (!audioRef.current) {
      audioRef.current = new Audio(url);
      audioRef.current.onended = () => setPlaying(false);
    }
    if (playing) {
      audioRef.current.pause();
      setPlaying(false);
    } else {
      audioRef.current.play();
      setPlaying(true);
    }
  };

  return (
    <button
      onClick={toggle}
      className="flex h-7 w-7 items-center justify-center rounded-full bg-primary/10 text-primary transition hover:bg-primary hover:text-primary-foreground"
    >
      {playing ? <Pause className="h-3 w-3" /> : <Play className="h-3 w-3 ml-0.5" />}
    </button>
  );
}

// ── Disposition Badge + Dropdown ──

const DISPOSITION_STYLES: Record<string, { bg: string; text: string; icon: React.ReactNode; label: string }> = {
  unreviewed: { bg: "bg-gray-100 dark:bg-gray-800", text: "text-gray-600 dark:text-gray-400", icon: <MoreHorizontal className="h-3 w-3" />, label: "New" },
  lead: { bg: "bg-emerald-100 dark:bg-emerald-950", text: "text-emerald-700 dark:text-emerald-300", icon: <UserPlus className="h-3 w-3" />, label: "Lead" },
  spam: { bg: "bg-red-100 dark:bg-red-950", text: "text-red-600 dark:text-red-400", icon: <ShieldAlert className="h-3 w-3" />, label: "Spam" },
  other: { bg: "bg-amber-100 dark:bg-amber-950", text: "text-amber-700 dark:text-amber-300", icon: <Eye className="h-3 w-3" />, label: "Other" },
};

function DispositionDropdown({
  current,
  onSelect,
}: {
  current: string;
  onSelect: (d: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const style = DISPOSITION_STYLES[current] || DISPOSITION_STYLES.unreviewed;

  // Close dropdown on outside click
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(!open)}
        className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold transition ${style.bg} ${style.text} hover:opacity-80`}
      >
        {style.icon}
        {style.label}
        <ChevronDown className="h-2.5 w-2.5 opacity-60" />
      </button>

      {open && (
        <div className="absolute left-0 top-full z-50 mt-1 w-28 rounded-lg border bg-popover shadow-lg">
          {Object.entries(DISPOSITION_STYLES).map(([key, s]) => (
            <button
              key={key}
              onClick={() => { onSelect(key); setOpen(false); }}
              className={`flex w-full items-center gap-2 px-3 py-1.5 text-xs transition hover:bg-muted ${
                current === key ? "font-semibold" : ""
              }`}
            >
              <span className={`${s.text}`}>{s.icon}</span>
              {s.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Main Page ──

export default function TrackingRoutingPage() {
  const business = useAppStore((s) => s.activeBusiness);
  const businessId = business?.id;
  const queryClient = useQueryClient();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [showAddForm, setShowAddForm] = useState(false);
  const [newNumber, setNewNumber] = useState("");
  const [newName, setNewName] = useState("");
  const [newIsMainline, setNewIsMainline] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);
  const [sortBy, setSortBy] = useState("date");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("desc");
  const [hideDispositioned, setHideDispositioned] = useState(true);

  const addNumberMutation = useMutation({
    mutationFn: (payload: { phone_number: string; campaign_name: string; friendly_name: string; line_type: string }) => {
      // Extract area code from the phone number for ACS provisioning
      const digits = payload.phone_number.replace(/\D/g, "");
      // US numbers: strip leading 1, take first 3 digits as area code
      const areaCode = digits.length === 11 && digits[0] === "1" ? digits.slice(1, 4) : digits.slice(0, 3);
      return provisionPhoneLine(
        businessId!,
        areaCode,
        payload.friendly_name || "mainline",
        "mainline",
      );
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["acs-numbers", businessId] });
      setNewNumber("");
      setNewName("");
      setNewIsMainline(false);
      setShowAddForm(false);
      setAddError(null);
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || "Failed to add number";
      setAddError(msg);
    },
  });

  const handleAddNumber = () => {
    if (!newNumber.trim()) return;
    // Normalize: strip spaces, dashes, parens — ensure E.164
    let num = newNumber.replace(/[\s\-()]/g, "");
    if (!num.startsWith("+")) num = "+1" + num;
    addNumberMutation.mutate({
      phone_number: num,
      campaign_name: newName || "Manual",
      friendly_name: newName || "",
      line_type: newIsMainline ? "mainline" : "campaign",
    });
  };

  const trackingNumbers = useQuery({
    queryKey: ["acs-numbers", businessId],
    queryFn: () => listACSNumbers(businessId!),
    enabled: !!businessId,
  });

  const callLog = useQuery({
    queryKey: ["tracking-calls", businessId, sortBy, sortOrder, hideDispositioned],
    queryFn: () =>
      listCalls(businessId!, {
        limit: 50,
        sort_by: sortBy,
        sort_order: sortOrder,
        hide_dispositioned: hideDispositioned,
      }),
    enabled: !!businessId,
  });

  const dispositionMutation = useMutation({
    mutationFn: ({ callId, disposition }: { callId: string; disposition: string }) =>
      dispositionCall(businessId!, callId, disposition),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["tracking-calls", businessId] });
    },
  });

  const deptSummary = useQuery({
    queryKey: ["tracking-dept-summary", businessId],
    queryFn: () => getDepartmentSummary(businessId!),
    enabled: !!businessId,
  });

  const phoneSettings = useQuery({
    queryKey: ["phone-settings", businessId],
    queryFn: () => getPhoneSettings(businessId!),
    enabled: !!businessId,
  });



  const allNumbers = trackingNumbers.data || [];
  const mainlineNumber = allNumbers.find(n => n.active && n.line_type === "mainline");
  const numbers = allNumbers.filter(n => n.line_type !== "mainline");
  const calls = callLog.data?.calls || [];
  const totalCalls = callLog.data?.total || 0;
  const departments = deptSummary.data || [];
  const isLoading = trackingNumbers.isLoading || callLog.isLoading;

  // Use configured departments from settings, fallback to defaults
  const configuredDepts = phoneSettings.data?.departments_config?.filter(d => d.enabled) || [];
  const displayDepts = configuredDepts.length > 0
    ? configuredDepts.map(d => d.name)
    : ["Sales", "Operations", "Finance", "Admin"];

  return (
    <div className="space-y-6 p-6">
      <PageHeader
        title="Tracking & Routing"
        description="How inbound calls flow from campaigns through your mainline to departments"
        actions={
          <Button size="sm" variant="outline" onClick={() => setSettingsOpen(true)}>
            <Settings className="mr-2 h-4 w-4" /> Settings
          </Button>
        }
      />

      {/* ═══ SECTION 1: ROUTING DIAGRAM ═══ */}
      <Card>
        <CardContent className="p-6">
          <h2 className="mb-4 text-sm font-semibold text-muted-foreground uppercase tracking-wider">
            Call Routing Architecture
          </h2>

          {allNumbers.length === 0 && !trackingNumbers.isLoading ? (
            <div className="rounded-lg border-2 border-dashed p-8 text-center">
              <PhoneForwarded className="mx-auto mb-3 h-8 w-8 text-muted-foreground" />
              <p className="text-sm text-muted-foreground">
                No phone lines configured yet. Add a phone line to see the routing diagram.
              </p>
            </div>
          ) : (
            <div className="flex items-center justify-center gap-4 overflow-x-auto py-4">
              {/* Left: Phone Lines */}
              <div className="flex flex-col gap-2 min-w-[200px]">
                <p className="mb-1 text-center text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
                  Phone Lines
                </p>
                {numbers.filter(n => n.active).map((tn) => (
                  <div
                    key={tn.id}
                    className="flex items-center gap-2 rounded-lg border bg-card px-3 py-2 text-xs transition hover:border-primary"
                  >
                    <div className="flex h-7 w-7 items-center justify-center rounded-md bg-primary/10 text-primary text-[10px]">
                      {CHANNEL_ICONS[tn.channel || ""] || "🌐"}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="font-semibold truncate">{tn.campaign_name}</div>
                      <div className="text-[10px] text-muted-foreground font-mono">{tn.phone_number}</div>
                    </div>
                  </div>
                ))}
              </div>

              {/* Arrow */}
              <div className="flex flex-col items-center gap-1">
                <ArrowRight className="h-5 w-5 text-primary" />
                <span className="text-[9px] text-muted-foreground">forwards to</span>
              </div>

              {/* Center: Mainline */}
              <div className="flex flex-col items-center min-w-[180px]">
                <p className="mb-1 text-center text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
                  Mainline
                </p>
                <div className="relative rounded-xl border-2 border-primary bg-primary/5 px-6 py-4 text-center">
                  <div className="absolute -right-1 -top-1 h-3 w-3 rounded-full bg-emerald-500">
                    <span className="absolute inset-0 animate-ping rounded-full bg-emerald-500 opacity-40" />
                  </div>
                  <Phone className="mx-auto mb-1 h-6 w-6 text-primary" />
                  <p className="font-bold text-sm text-primary">Main Line</p>
                  {mainlineNumber && (
                    <p className="text-[11px] font-mono text-primary/70 mt-0.5">{mainlineNumber.phone_number}</p>
                  )}
                  <div className="mt-2 space-y-1 text-[10px] text-muted-foreground">
                    <p>✓ AI greeting & name capture</p>
                    <p>✓ All calls recorded</p>
                    <p>✓ Auto-transcription</p>
                    <p>✓ Intent-based routing</p>
                  </div>
                </div>
              </div>

              {/* Arrow */}
              <div className="flex flex-col items-center gap-1">
                <ArrowRight className="h-5 w-5 text-muted-foreground" />
                <span className="text-[9px] text-muted-foreground">routes to</span>
              </div>

              {/* Right: Departments */}
              <div className="flex flex-col gap-2 min-w-[180px]">
                <p className="mb-1 text-center text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
                  Departments
                </p>
                {displayDepts.map((dept) => (
                  <div
                    key={dept}
                    className="flex items-center gap-2 rounded-lg border bg-card px-3 py-2 text-xs transition hover:border-muted-foreground"
                  >
                    <div className={`flex h-7 w-7 items-center justify-center rounded-md text-[10px] ${getDeptColor(dept)}`}>
                      {dept === "Sales" ? "💰" : dept === "Operations" ? "⚙" : dept === "Finance" ? "💳" : "🏢"}
                    </div>
                    <div className="flex-1">
                      <div className="font-semibold">{dept}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* ═══ SECTION 2: PHONE NUMBERS ═══ */}
      <Card>
        <CardContent className="p-0">
          <div className="flex items-center justify-between border-b px-4 py-3">
            <h2 className="text-sm font-semibold">
              Phone Lines
              <span className="ml-2 text-xs font-normal text-muted-foreground">
                {allNumbers.length} total
              </span>
            </h2>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowAddForm(!showAddForm)}
            >
              {showAddForm ? <X className="mr-1.5 h-3.5 w-3.5" /> : <Plus className="mr-1.5 h-3.5 w-3.5" />}
              {showAddForm ? "Cancel" : "Add Number"}
            </Button>
          </div>

          {/* Add Number Form */}
          {showAddForm && (
            <div className="border-b bg-muted/30 px-4 py-4 space-y-3">
              {addError && (
                <p className="text-xs text-red-600">{addError}</p>
              )}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div className="space-y-1">
                  <label className="text-[10px] font-medium text-muted-foreground">Phone Number</label>
                  <Input
                    value={newNumber}
                    onChange={(e) => setNewNumber(e.target.value)}
                    placeholder="+1 (940) 337-6016"
                    className="text-sm h-8 font-mono"
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-[10px] font-medium text-muted-foreground">Friendly Name</label>
                  <Input
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                    placeholder="e.g., Christian's Phone"
                    className="text-sm h-8"
                  />
                </div>
                <div className="flex items-end gap-3">
                  <label className="flex items-center gap-2 cursor-pointer text-xs pb-1.5">
                    <input
                      type="checkbox"
                      checked={newIsMainline}
                      onChange={(e) => setNewIsMainline(e.target.checked)}
                      className="h-3.5 w-3.5 rounded border accent-primary"
                    />
                    Mainline
                  </label>
                  <Button
                    size="sm"
                    onClick={handleAddNumber}
                    disabled={addNumberMutation.isPending || !newNumber.trim()}
                    className="h-8"
                  >
                    {addNumberMutation.isPending ? (
                      <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Plus className="mr-1.5 h-3.5 w-3.5" />
                    )}
                    Add
                  </Button>
                </div>
              </div>
              <p className="text-[10px] text-muted-foreground">
                Add any phone number you own. It will appear in the department routing settings once added.
              </p>
            </div>
          )}

          {/* Number List */}
          {allNumbers.length === 0 ? (
            <div className="py-8 text-center text-sm text-muted-foreground">
              No phone numbers added yet.
            </div>
          ) : (
            <div className="divide-y">
              {allNumbers.map((tn) => (
                <div key={tn.id} className="flex items-center gap-3 px-4 py-2.5 text-sm">
                  <div className="flex h-8 w-8 items-center justify-center rounded-md bg-primary/10 text-primary text-xs">
                    {tn.line_type === "mainline" ? "📞" : CHANNEL_ICONS[tn.channel || ""] || "🌐"}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-medium truncate">
                        {tn.friendly_name || tn.campaign_name}
                      </span>
                      {tn.line_type === "mainline" && (
                        <span className="inline-block rounded-full bg-primary/10 text-primary px-2 py-0.5 text-[10px] font-semibold">
                          Mainline
                        </span>
                      )}
                      {!tn.active && (
                        <span className="inline-block rounded-full bg-red-100 text-red-600 px-2 py-0.5 text-[10px] font-semibold">
                          Inactive
                        </span>
                      )}
                    </div>
                    <span className="text-[11px] text-muted-foreground font-mono">{tn.phone_number}</span>
                  </div>
                  <span className="text-[10px] text-muted-foreground whitespace-nowrap">
                    {tn.channel || "manual"}
                  </span>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* ═══ SECTION 3: PHONE LINE PERFORMANCE ═══ */}
      <Card>
        <CardContent className="p-0">
          <div className="flex items-center justify-between border-b px-4 py-3">
            <h2 className="text-sm font-semibold">
              Phone Line Performance
              {allNumbers.length > 0 && (
                <span className="ml-2 text-xs font-normal text-muted-foreground">
                  {totalCalls} total calls
                </span>
              )}
            </h2>
          </div>

          {trackingNumbers.isLoading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : allNumbers.length === 0 ? (
            <div className="py-12 text-center text-sm text-muted-foreground">
              No phone numbers configured. Provision a mainline number to get started.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/50 text-xs uppercase tracking-wider text-muted-foreground">
                    <th className="px-3 py-2 text-left">Phone Line</th>
                    <th className="px-3 py-2 text-left">Type</th>
                    <th className="px-3 py-2 text-left">Campaign</th>
                  </tr>
                </thead>
                <tbody>
                  {allNumbers.map((tn) => {
                    const formattedNumber = tn.phone_number.replace(/^\+1(\d{3})(\d{3})(\d{4})$/, "($1) $2-$3");
                    return (
                      <tr key={tn.phone_number} className="border-b transition hover:bg-muted/30">
                        <td className="px-3 py-2.5">
                          <div className="flex items-center gap-2">
                            <div className="flex h-7 w-7 items-center justify-center rounded-md bg-primary/10 text-primary text-[10px]">
                              {tn.line_type === "mainline" ? "📞" : CHANNEL_ICONS[tn.channel || ""] || "🌐"}
                            </div>
                            <div>
                              <div className="font-medium font-mono text-xs">{formattedNumber}</div>
                              {tn.friendly_name && (
                                <div className="text-[10px] text-muted-foreground">{tn.friendly_name}</div>
                              )}
                            </div>
                            {tn.line_type === "mainline" && (
                              <span className="inline-block rounded-full bg-primary/10 text-primary px-1.5 py-0.5 text-[9px] font-semibold">
                                Main
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="px-3 py-2.5 text-xs text-muted-foreground capitalize">
                          {tn.line_type}
                        </td>
                        <td className="px-3 py-2.5">
                          <span className={`inline-block rounded-full px-2 py-0.5 text-[11px] font-semibold ${getCampaignColor(tn.channel, tn.campaign_name ?? null)}`}>
                            {tn.campaign_name ?? "—"}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* ═══ SECTION 4: DEPARTMENT ATTRIBUTION SUMMARY ═══ */}
      <Card>
        <CardContent className="p-0">
          <div className="flex items-center justify-between border-b px-4 py-3">
            <h2 className="text-sm font-semibold">Department Attribution</h2>
          </div>

          {departments.length === 0 && !deptSummary.isLoading ? (
            <div className="py-8 text-center text-sm text-muted-foreground">
              Department attribution will appear once calls are routed.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/50 text-xs uppercase tracking-wider text-muted-foreground">
                    <th className="px-3 py-2 text-left">Department</th>
                    <th className="px-3 py-2 text-left">Total Calls</th>
                    <th className="px-3 py-2 text-left">Avg Duration</th>
                    <th className="px-3 py-2 text-left">Completed</th>
                    <th className="px-3 py-2 text-left">Follow-Up</th>
                    <th className="px-3 py-2 text-left">Top Source</th>
                    <th className="px-3 py-2 text-left w-24">Volume</th>
                  </tr>
                </thead>
                <tbody>
                  {departments.map((dept) => {
                    const maxCalls = Math.max(...departments.map(d => d.total_calls), 1);
                    const pct = (dept.total_calls / maxCalls) * 100;
                    return (
                      <tr key={dept.department} className="border-b transition hover:bg-muted/30">
                        <td className="px-3 py-2.5">
                          <span className={`inline-block rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${getDeptColor(dept.department)}`}>
                            {dept.department}
                          </span>
                        </td>
                        <td className="px-3 py-2.5 font-semibold">{dept.total_calls}</td>
                        <td className="px-3 py-2.5 text-xs font-mono text-muted-foreground">
                          {formatDuration(Math.round(dept.avg_duration_s))}
                        </td>
                        <td className="px-3 py-2.5">
                          <span className="font-semibold">{dept.completed_count}</span>
                          <span className="ml-1 text-xs text-emerald-600">({dept.completed_pct}%)</span>
                        </td>
                        <td className="px-3 py-2.5 font-semibold">{dept.followup_count}</td>
                        <td className="px-3 py-2.5 text-xs">
                          {dept.top_campaign || "—"}
                          {dept.top_campaign_count > 0 && (
                            <span className="ml-1 text-muted-foreground">({dept.top_campaign_count})</span>
                          )}
                        </td>
                        <td className="px-3 py-2.5">
                          <div className="h-1.5 w-full rounded-full bg-muted overflow-hidden">
                            <div
                              className="h-full rounded-full bg-primary transition-all"
                              style={{ width: `${pct}%` }}
                            />
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Settings Modal */}
      <SettingsModal
        isOpen={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        businessId={businessId}
        mainlineNumber={mainlineNumber?.phone_number}
      />
    </div>
  );
}
