import { useAppStore } from "@/shared/stores/app-store";

/**
 * Returns helpers to check the current user's permissions.
 *
 * Usage:
 *   const { can, hasRole, isGlobalAdmin } = usePermissions();
 *   if (can("assign_leads")) { ... }
 *   if (hasRole("sales_executive")) { ... }
 */
export function usePermissions() {
  const permissions = useAppStore((s) => s.permissions);
  const roles = useAppStore((s) => s.roles);

  const isGlobalAdmin = roles.includes("global_admin") || permissions.includes("*");

  function can(permission: string): boolean {
    return isGlobalAdmin || permissions.includes(permission);
  }

  function hasRole(role: string): boolean {
    return roles.includes(role);
  }

  function canAny(...perms: string[]): boolean {
    return perms.some((p) => can(p));
  }

  function canAll(...perms: string[]): boolean {
    return perms.every((p) => can(p));
  }

  return { can, hasRole, canAny, canAll, isGlobalAdmin, roles, permissions };
}
