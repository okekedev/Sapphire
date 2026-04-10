import { create } from "zustand";
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

  // Business
  activeBusiness: Business | null;
  setActiveBusiness: (biz: Business) => void;
  /** null = all tabs (owner). string[] = specific tabs the member can see. */
  allowedTabs: string[] | null;
  setAllowedTabs: (tabs: string[] | null) => void;

  // Workspace
  selectedDepartment: Department;
  setSelectedDepartment: (dept: Department) => void;
}


export const useAppStore = create<AppState>((set) => ({
  // Auth
  accessToken: localStorage.getItem("auth-token"),
  refreshToken: localStorage.getItem("refresh-token"),
  user: null,
  setTokens: (access, refresh) => {
    localStorage.setItem("auth-token", access);
    localStorage.setItem("refresh-token", refresh);
    set({ accessToken: access, refreshToken: refresh });
  },
  setUser: (user) => set({ user }),
  logout: () => {
    localStorage.removeItem("auth-token");
    localStorage.removeItem("refresh-token");
    set({ accessToken: null, refreshToken: null, user: null, activeBusiness: null, allowedTabs: null });
  },

  // Business
  activeBusiness: null,
  setActiveBusiness: (biz) => set({ activeBusiness: biz }),
  allowedTabs: null,
  setAllowedTabs: (tabs) => set({ allowedTabs: tabs }),

  // Workspace
  selectedDepartment: "marketing",
  setSelectedDepartment: (dept) => set({ selectedDepartment: dept }),
}));
