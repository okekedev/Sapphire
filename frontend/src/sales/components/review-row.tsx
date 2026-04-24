import { useState } from "react";
import { Clock } from "lucide-react";
import { formatDuration, formatDateShort } from "@/shared/lib/format";
import { cn } from "@/shared/lib/utils";
import type { ReviewItem } from "@/sales/api/sales";

export type { ReviewItem };

const CALL_OUTCOME_STYLES: Record<string, string> = {
  Lead:      "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300",
  "No Lead": "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400",
};

const LEAD_OUTCOME_STYLES: Record<string, string> = {
  Converted:       "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300",
  "No Conversion": "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300",
  Pending:         "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
};

function buildContextText(item: ReviewItem): string {
  const parts: string[] = [];
  if (item.call_summary) parts.push(item.call_summary);
  if (item.lead_summary) parts.push(`Lead: ${item.lead_summary}`);
  if (item.no_lead_reason) parts.push(`No-lead: ${item.no_lead_reason}`);
  if (item.no_conversion_reason) parts.push(`No-conversion: ${item.no_conversion_reason}`);
  return parts.join(" | ") || "—";
}

export function exportReviewCSV(items: ReviewItem[]) {
  const headers = ["Name", "Phone", "Call Outcome", "Lead Outcome", "Customer", "Context", "Date"];
  const rows = items.map((item) => [
    item.caller_name || "",
    item.caller_phone || "",
    item.call_outcome || "",
    item.lead_outcome || "",
    item.customer_type ? (item.customer_type === "returning" ? "Returning" : "New") : "",
    buildContextText(item).replace(/"/g, '""'),
    item.created_at ? new Date(item.created_at).toLocaleDateString() : "",
  ]);
  const csv = [headers.join(","), ...rows.map((r) => r.map((c) => `"${c}"`).join(","))].join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `sales-review-${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

export function ReviewRow({ item }: { item: ReviewItem }) {
  const [expanded, setExpanded] = useState(false);
  const callCls = CALL_OUTCOME_STYLES[item.call_outcome] ?? CALL_OUTCOME_STYLES["No Lead"];
  const leadCls = item.lead_outcome ? LEAD_OUTCOME_STYLES[item.lead_outcome] : null;

  return (
    <>
      <tr className="border-b transition hover:bg-muted/30 cursor-pointer" onClick={() => setExpanded(!expanded)}>
        <td className="px-3 py-2.5"><span className="font-medium text-sm">{item.caller_name || "Unknown"}</span></td>
        <td className="px-3 py-2.5 text-xs font-mono text-muted-foreground">{item.caller_phone || "—"}</td>
        <td className="px-3 py-2.5">
          <span className={cn("rounded-full px-2 py-0.5 text-[10px] font-semibold", callCls)}>{item.call_outcome}</span>
        </td>
        <td className="px-3 py-2.5">
          {leadCls ? (
            <span className={cn("rounded-full px-2 py-0.5 text-[10px] font-semibold", leadCls)}>{item.lead_outcome}</span>
          ) : (
            <span className="text-xs text-muted-foreground">—</span>
          )}
        </td>
        <td className="px-3 py-2.5">
          {item.customer_type === "returning" ? (
            <span className="rounded-full bg-violet-100 px-2 py-0.5 text-[10px] font-semibold text-violet-700 dark:bg-violet-950 dark:text-violet-300">Returning</span>
          ) : item.customer_type === "new" ? (
            <span className="rounded-full bg-sky-100 px-2 py-0.5 text-[10px] font-semibold text-sky-700 dark:bg-sky-950 dark:text-sky-300">New</span>
          ) : (
            <span className="text-xs text-muted-foreground">—</span>
          )}
        </td>
        <td className="px-3 py-2.5 text-xs text-muted-foreground max-w-[250px] truncate">{buildContextText(item)}</td>
        <td className="px-3 py-2.5 text-xs text-muted-foreground">{formatDateShort(item.created_at)}</td>
      </tr>
      {expanded && (
        <tr className="border-b bg-muted/20">
          <td colSpan={7} className="px-4 py-3 space-y-2">
            {item.call_summary && (
              <div>
                <p className="text-[10px] font-semibold uppercase text-muted-foreground mb-0.5">Call Summary</p>
                <p className="text-xs leading-relaxed">{item.call_summary}</p>
              </div>
            )}
            {item.lead_summary && (
              <div>
                <p className="text-[10px] font-semibold uppercase text-muted-foreground mb-0.5">Lead Context</p>
                <p className="text-xs leading-relaxed">{item.lead_summary}</p>
              </div>
            )}
            {item.no_lead_reason && (
              <div>
                <p className="text-[10px] font-semibold uppercase text-muted-foreground mb-0.5">No-Lead Reason</p>
                <p className="text-xs leading-relaxed">{item.no_lead_reason}</p>
              </div>
            )}
            {item.no_conversion_reason && (
              <div>
                <p className="text-[10px] font-semibold uppercase text-muted-foreground mb-0.5">No-Conversion Reason</p>
                <p className="text-xs leading-relaxed">{item.no_conversion_reason}</p>
              </div>
            )}
            <div className="flex items-center gap-4 text-[11px] text-muted-foreground">
              {item.duration_s != null && (
                <span className="flex items-center gap-1"><Clock className="h-3 w-3" /> {formatDuration(item.duration_s)}</span>
              )}
              {item.converted_job_id && (
                <span className="text-primary font-medium">Job: {item.converted_job_id.slice(0, 8)}…</span>
              )}
            </div>
            {item.recording_url && <audio controls src={item.recording_url} className="w-full h-8" preload="none" />}
          </td>
        </tr>
      )}
    </>
  );
}
