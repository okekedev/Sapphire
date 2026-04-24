import { useQuery } from "@tanstack/react-query";
import { PhoneIncoming, Download, Clock } from "lucide-react";
import { useAppStore } from "@/shared/stores/app-store";
import { listCalls } from "@/marketing/api/tracking-routing";

export default function CallReportsPage() {
  const business = useAppStore((s) => s.activeBusiness);
  const bizId = business?.id ?? "";

  const { data: callLogData } = useQuery({
    queryKey: ["call-log", bizId],
    queryFn: () => listCalls(bizId, { limit: 100, sort_by: "date", sort_order: "desc" }),
    enabled: !!bizId,
    refetchInterval: 30_000,
  });

  const exportCSV = () => {
    const calls = callLogData?.calls ?? [];
    if (!calls.length) return;
    const rows = calls.map((c) => ({
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
  };

  const calls = callLogData?.calls ?? [];

  return (
    <div className="p-4 md:p-6">
      <div className="flex items-center justify-between mb-5">
        <p className="text-sm font-semibold">Call Log</p>
        {calls.length > 0 && (
          <button
            onClick={exportCSV}
            className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-xs font-medium text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
          >
            <Download size={13} />
            Export CSV
          </button>
        )}
      </div>

      {calls.length === 0 ? (
        <div className="text-center py-16 text-sm text-muted-foreground">
          <PhoneIncoming size={32} className="mx-auto mb-2 opacity-40" />
          <p>No inbound calls yet.</p>
          <p className="text-xs mt-1">Calls will appear here as they come in through your tracking numbers.</p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
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
              {calls.map((call) => (
                <tr key={call.id} className="hover:bg-muted/30 transition-colors">
                  <td className="px-3 py-2 font-mono text-xs whitespace-nowrap">
                    {call.caller_phone
                      ? call.caller_phone.replace(/^\+1(\d{3})(\d{3})(\d{4})$/, "($1) $2-$3")
                      : "—"}
                  </td>
                  <td className="px-3 py-2 whitespace-nowrap">
                    {call.caller_name || <span className="text-muted-foreground">Unknown</span>}
                  </td>
                  <td className="px-3 py-2 max-w-[220px] truncate text-muted-foreground">
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
  );
}
