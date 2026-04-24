/** Lead score badge — Hot / Warm / Cold based on 0–1 score value. */

export function ScoreBadge({ score }: { score: string | number | null | undefined }) {
  const s = score == null ? NaN : typeof score === "number" ? score : parseFloat(score as string);
  if (isNaN(s)) return null;
  if (s >= 0.7) return (
    <span className="rounded-full bg-red-100 px-2 py-0.5 text-[10px] font-semibold text-red-700 dark:bg-red-900/40 dark:text-red-300">
      Hot
    </span>
  );
  if (s >= 0.4) return (
    <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold text-amber-700 dark:bg-amber-900/40 dark:text-amber-300">
      Warm
    </span>
  );
  return (
    <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold text-slate-500 dark:bg-slate-800 dark:text-slate-400">
      Cold
    </span>
  );
}
