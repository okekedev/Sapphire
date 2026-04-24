import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { X, Send, Loader2, Calendar, MapPin, User } from "lucide-react";
import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { cn } from "@/shared/lib/utils";
import { listStaff } from "@/operations/api/staff";
import type { JobItem } from "@/sales/api/sales";
import type { JobTemplate } from "@/operations/api/job-templates";

interface Props {
  job: JobItem;
  template: JobTemplate | null;
  businessId: string;
  onDispatch: (data: { assigned_to: string; service_address?: string; scheduled_at?: string }) => void;
  onClose: () => void;
  isPending: boolean;
}

export function JobDispatchSheet({ job, template, businessId, onDispatch, onClose, isPending }: Props) {
  const [assignedTo, setAssignedTo] = useState(job.assigned_to ?? "");
  const [address, setAddress] = useState(job.service_address ?? "");
  const [scheduledDate, setScheduledDate] = useState("");
  const [scheduledTime, setScheduledTime] = useState("");

  const { data: staff = [] } = useQuery({
    queryKey: ["staff", businessId],
    queryFn: () => listStaff(businessId),
    enabled: !!businessId,
  });

  const requiresScheduling = template?.requires_scheduling ?? false;
  const selectedStaff = staff.find((s) => s.id === assignedTo);

  const scheduledAt = scheduledDate && scheduledTime
    ? new Date(`${scheduledDate}T${scheduledTime}`).toISOString()
    : undefined;

  // SMS preview
  const smsPreview = selectedStaff
    ? `Hi ${selectedStaff.first_name}, you've been assigned to: ${job.title}${address ? ` at ${address}` : ""}${scheduledDate && scheduledTime ? ` on ${new Date(`${scheduledDate}T${scheduledTime}`).toLocaleDateString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}` : ""}. Reply START when on site.`
    : null;

  const canDispatch = !!assignedTo && (!requiresScheduling || (!!scheduledDate && !!scheduledTime));

  const handleDispatch = () => {
    if (!canDispatch) return;
    onDispatch({
      assigned_to: assignedTo,
      service_address: address || undefined,
      scheduled_at: scheduledAt,
    });
  };

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 z-40 bg-black/40" onClick={onClose} />

      {/* Sheet */}
      <div className="fixed right-0 top-0 bottom-0 z-50 w-full max-w-sm bg-card border-l border-border shadow-xl flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-border">
          <div>
            <p className="text-sm font-semibold">Assign & Dispatch</p>
            <p className="text-xs text-muted-foreground truncate max-w-[220px]">{job.title}</p>
          </div>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X size={16} />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {/* Assign to */}
          <div className="space-y-1.5">
            <label className="text-xs font-medium flex items-center gap-1.5">
              <User className="h-3.5 w-3.5 text-muted-foreground" /> Assign to *
            </label>
            <select
              value={assignedTo}
              onChange={(e) => setAssignedTo(e.target.value)}
              className="w-full h-8 rounded-md border border-border bg-background px-2 text-sm"
            >
              <option value="">Select staff member...</option>
              {staff.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.first_name} {s.last_name ?? ""} — {s.role}
                </option>
              ))}
            </select>
            {staff.length === 0 && (
              <p className="text-[11px] text-muted-foreground">No staff added yet. Add team members in the Team tab.</p>
            )}
          </div>

          {/* Service address */}
          <div className="space-y-1.5">
            <label className="text-xs font-medium flex items-center gap-1.5">
              <MapPin className="h-3.5 w-3.5 text-muted-foreground" /> Service Address
            </label>
            <Input
              value={address}
              onChange={(e) => setAddress(e.target.value)}
              placeholder="123 Main St, City, State"
              className="text-sm h-8"
            />
          </div>

          {/* Scheduled date/time — only if template requires it */}
          {requiresScheduling && (
            <div className="space-y-1.5">
              <label className="text-xs font-medium flex items-center gap-1.5">
                <Calendar className="h-3.5 w-3.5 text-muted-foreground" /> Scheduled Date & Time *
              </label>
              <div className="grid grid-cols-2 gap-2">
                <Input
                  type="date"
                  value={scheduledDate}
                  onChange={(e) => setScheduledDate(e.target.value)}
                  className="text-sm h-8"
                />
                <Input
                  type="time"
                  value={scheduledTime}
                  onChange={(e) => setScheduledTime(e.target.value)}
                  className="text-sm h-8"
                />
              </div>
            </div>
          )}

          {/* SMS preview */}
          {smsPreview && (
            <div className="rounded-md border border-blue-200 bg-blue-50/50 dark:border-blue-800 dark:bg-blue-950/30 p-3 space-y-1">
              <p className="text-[10px] font-semibold uppercase tracking-wider text-blue-600 dark:text-blue-400">SMS Preview</p>
              <p className="text-xs text-foreground/80 leading-relaxed">{smsPreview}</p>
              {!selectedStaff?.phone && (
                <p className="text-[11px] text-amber-600 dark:text-amber-400">⚠ No phone number on file — SMS will not be sent.</p>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="border-t border-border p-4">
          <Button
            className="w-full"
            onClick={handleDispatch}
            disabled={!canDispatch || isPending}
          >
            {isPending ? (
              <Loader2 className="h-4 w-4 animate-spin mr-2" />
            ) : (
              <Send className="h-4 w-4 mr-2" />
            )}
            {selectedStaff?.phone ? "Dispatch & Send SMS" : "Dispatch (no SMS)"}
          </Button>
        </div>
      </div>
    </>
  );
}
