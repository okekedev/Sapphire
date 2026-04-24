import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import type { User } from "@/shared/types/auth";
import type { Business } from "@/shared/types/business";
import type { Department } from "@/shared/types/workspace";

interface AppState {
  // Auth
  accessToken: string | null;
  refreshToken: string | null;
  user: User | null;
  setTokens: (access: string, refresh: string) => void;
  setUser: (user: User) => void;
  logout: () => void;

  // RBAC — roles + permissions loaded from /auth/me after login
  roles: string[];        // e.g. ["sales_executive", "analyst"]
  permissions: string[];  // e.g. ["access_sales", "assign_leads", ...]
  setRolesAndPermissions: (roles: string[], permissions: string[]) => void;

  // Business
  activeBusiness: Business | null;
  setActiveBusiness: (biz: Business) => void;

  // Workspace
  selectedDepartment: Department;
  setSelectedDepartment: (dept: Department) => void;
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      // Auth
      accessToken: null,
      refreshToken: null,
      user: null,
      setTokens: (access, refresh) => set({ accessToken: access, refreshToken: refresh }),
      setUser: (user) => set({ user }),
      logout: () => set({
        accessToken: null, refreshToken: null, user: null,
        activeBusiness: null, roles: [], permissions: [],
      }),

      // RBAC
      roles: [],
      permissions: [],
      setRolesAndPermissions: (roles, permissions) => set({ roles, permissions }),

      // Business
      activeBusiness: null,
      setActiveBusiness: (biz) => set({ activeBusiness: biz }),

      // Workspace
      selectedDepartment: "marketing",
      setSelectedDepartment: (dept) => set({ selectedDepartment: dept }),
    }),
    {
      name: "app-auth",
      storage: createJSONStorage(() => localStorage),
      // Only persist auth tokens — everything else reloaded from API on mount
      partialize: (state) => ({
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
      }),
    },
  ),
);
