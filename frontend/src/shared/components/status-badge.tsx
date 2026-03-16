import { cn } from "@/shared/lib/utils";
import { STATUS_COLORS } from "@/shared/lib/constants";

export function StatusBadge({ status }: { status: string }) {
  const colorClass = STATUS_COLORS[status] ?? "bg-gray-100 text-gray-600";
  return (
    <span className={cn("inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium", colorClass)}>
      {status.replace(/_/g, " ")}
    </span>
  );
}
