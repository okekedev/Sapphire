/**
 * Centralized query key factories for TanStack Query.
 * Use these everywhere instead of inline string arrays to prevent typos
 * and enable precise cache invalidation.
 *
 * Pattern: invalidate the broadest key you need:
 *   queryClient.invalidateQueries({ queryKey: salesKeys.all })  // all sales data
 *   queryClient.invalidateQueries({ queryKey: salesKeys.prospects(bizId) }) // just prospects
 */

export const salesKeys = {
  all: ["sales"] as const,
  pipelineSummary: (bizId: string) => ["sales-pipeline-summary", bizId] as const,
  prospects:       (bizId: string) => ["sales-prospects", bizId] as const,
  leads:           (bizId: string) => ["sales-leads", bizId] as const,
  review:          (bizId: string, disposition: string) => ["sales-review", bizId, disposition] as const,
  departments:     (bizId: string) => ["sales-departments", bizId] as const,
  employees:       (bizId: string, deptId: string) => ["sales-employees", bizId, deptId] as const,
};

export const contactKeys = {
  list:   (bizId: string, filter?: string, search?: string) => ["contacts", bizId, filter, search] as const,
  detail: (contactId: string) => ["contact", contactId] as const,
  jobs:   (contactId: string, bizId: string) => ["jobs-for-contact", contactId, bizId] as const,
};

export const businessKeys = {
  all:        ["businesses"] as const,
  membership: (bizId: string) => ["my-membership", bizId] as const,
};

export const opsKeys = {
  jobs:     (bizId: string) => ["ops-jobs", bizId] as const,
  summary:  (bizId: string) => ["ops-summary", bizId] as const,
  customers:(bizId: string) => ["ops-customers", bizId] as const,
};

export const dashboardKeys = {
  summary: (bizId: string) => ["dashboard-summary", bizId] as const,
};

export const orgKeys = {
  list:   (bizId: string, search?: string) => ["organizations", bizId, search] as const,
  detail: (orgId: string) => ["organization", orgId] as const,
};
