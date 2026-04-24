/** Shared contact status badge styles used across Contacts, Contact Detail, and Sales pages. */

export type ContactStatus = "new" | "prospect" | "active_customer" | "no_conversion" | "churned" | "other";

export const STATUS_BADGE: Record<string, { label: string; cls: string }> = {
  new:             { label: "New",      cls: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300" },
  prospect:        { label: "Prospect", cls: "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300" },
  active_customer: { label: "Customer", cls: "bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300" },
  no_conversion:   { label: "No Conv.", cls: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300" },
  churned:         { label: "Churned",  cls: "bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400" },
  other:           { label: "Other",    cls: "bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400" },
};
