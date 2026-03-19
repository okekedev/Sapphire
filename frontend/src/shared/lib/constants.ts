export const API_BASE = "/api/v1";

export const STATUS_COLORS: Record<string, string> = {
  active: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300",
  running: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300",
  completed: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300",
  failed: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300",
  error: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300",
  paused: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300",
  draft: "bg-gray-100 text-gray-600 dark:bg-gray-800/30 dark:text-gray-400",
  pending: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300",
  connected: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300",
  disconnected: "bg-gray-100 text-gray-500 dark:bg-gray-800/30 dark:text-gray-400",
  expired: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300",
};

/** Platforms connected via OAuth (user-initiated per business) */
export const OAUTH_PLATFORMS = [
  "google_business_profile",
  "google_ads",
  "facebook",
  "bing",
  "linkedin",
] as const;

export const PLATFORM_LABELS: Record<string, string> = {
  google_business_profile: "Google Business",
  google_ads: "Google Ads",
  facebook: "Meta (FB + IG)",
  instagram: "Instagram",
  bing: "Bing Ads",
  linkedin: "LinkedIn",
};

/** Approval status for each OAuth platform */
export const PLATFORM_STATUS: Record<string, "live" | "pending" | "needs_approval"> = {
  google_business_profile: "live",
  google_ads: "live",
  facebook: "live",
  bing: "live",
  linkedin: "needs_approval",
};
