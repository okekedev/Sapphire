/** Shared formatting utilities used across sales, contacts, and operations. */

export function formatDuration(seconds: number | null | undefined): string {
  if (!seconds) return "—";
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

export function formatDateShort(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export function formatCurrency(amount: number | null | undefined): string {
  if (amount == null) return "—";
  return `$${amount.toLocaleString()}`;
}
