import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { PhoneIncoming, X, ArrowRight } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useAppStore } from "@/shared/stores/app-store";
import { getDashboardSummary } from "@/shared/api/dashboard";

export function CallActionPrompt() {
  const navigate = useNavigate();
  const business = useAppStore((s) => s.activeBusiness);
  const businessId = business?.id ?? "";

  const [visible, setVisible] = useState(false);
  const prevCount = useRef<number | null>(null);

  const { data } = useQuery({
    queryKey: ["dashboard-summary", businessId],
    queryFn: () => getDashboardSummary(businessId),
    enabled: !!businessId,
    refetchInterval: 20_000,
  });

  const count = data?.unreviewed_calls ?? 0;

  useEffect(() => {
    if (prevCount.current !== null && count > prevCount.current) {
      setVisible(true);
    }
    prevCount.current = count;
  }, [count]);

  if (!visible || count === 0) return null;

  return (
    <div className="fixed bottom-4 left-1/2 z-50 w-full max-w-sm -translate-x-1/2 px-4">
      <div className="flex items-start gap-3 rounded-xl border border-border bg-card shadow-lg p-4">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-blue-100 dark:bg-blue-900/40">
          <PhoneIncoming className="h-4 w-4 text-blue-600 dark:text-blue-400" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold">
            {count} new call{count !== 1 ? "s" : ""} to review
          </p>
          <p className="mt-0.5 text-xs text-muted-foreground">
            New inbound calls waiting for qualification
          </p>
          <button
            type="button"
            onClick={() => { navigate("/sales"); setVisible(false); }}
            className="mt-2 flex items-center gap-1 text-xs font-medium text-primary hover:underline"
          >
            Review now <ArrowRight size={11} />
          </button>
        </div>
        <button
          type="button"
          onClick={() => setVisible(false)}
          className="shrink-0 text-muted-foreground hover:text-foreground transition-colors"
        >
          <X size={14} />
        </button>
      </div>
    </div>
  );
}
