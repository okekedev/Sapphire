import { create } from "zustand";
import type { SetupStep } from "@/shared/types/organization";

interface SetupState {
  // Steps
  currentStep: SetupStep;
  claudeConnected: boolean;
  profileComplete: boolean;
  templateChosen: boolean;
  setupDismissed: boolean;

  // Legacy compat
  orgSeeded: boolean;

  // Actions
  setClaudeConnected: (connected: boolean) => void;
  setProfileComplete: (complete: boolean) => void;
  setOrgSeeded: (seeded: boolean) => void;
  setTemplateChosen: (chosen: boolean) => void;
  setCurrentStep: (step: SetupStep) => void;
  dismissSetup: () => void;
  isSetupComplete: () => boolean;
}

function loadSetupState() {
  try {
    const stored = localStorage.getItem("app-setup");
    if (!stored) return { claudeConnected: true, profileComplete: false, templateChosen: false, setupDismissed: false };
    const parsed = JSON.parse(stored);
    return {
      claudeConnected: true, // AI provider (Foundry) is always available — no CLI needed
      profileComplete: parsed.profileComplete ?? parsed.orgSeeded ?? false,
      templateChosen: parsed.templateChosen ?? false,
      setupDismissed: parsed.setupDismissed ?? false,
    };
  } catch {
    return { claudeConnected: true, profileComplete: false, templateChosen: false, setupDismissed: false };
  }
}

function persistSetup(state: {
  claudeConnected: boolean;
  profileComplete: boolean;
  templateChosen: boolean;
  setupDismissed: boolean;
}) {
  localStorage.setItem("app-setup", JSON.stringify(state));
}

const initial = loadSetupState();

export const useSetupStore = create<SetupState>((set, get) => ({
  currentStep: initial.claudeConnected
    ? initial.profileComplete
      ? "template"
      : "organization"
    : "connect",
  claudeConnected: initial.claudeConnected,
  profileComplete: initial.profileComplete,
  orgSeeded: initial.profileComplete, // legacy alias
  templateChosen: initial.templateChosen,
  setupDismissed: initial.setupDismissed,

  setClaudeConnected: (connected) => {
    set({ claudeConnected: connected, currentStep: connected ? "organization" : "connect" });
    const s = get();
    persistSetup({ claudeConnected: connected, profileComplete: s.profileComplete, templateChosen: s.templateChosen, setupDismissed: s.setupDismissed });
  },
  setProfileComplete: (complete) => {
    set({ profileComplete: complete, orgSeeded: complete, currentStep: complete ? "template" : "organization" });
    const s = get();
    persistSetup({ claudeConnected: s.claudeConnected, profileComplete: complete, templateChosen: s.templateChosen, setupDismissed: s.setupDismissed });
  },
  setOrgSeeded: (seeded) => {
    // Legacy — maps to profileComplete
    set({ orgSeeded: seeded, profileComplete: seeded, currentStep: seeded ? "template" : "organization" });
    const s = get();
    persistSetup({ claudeConnected: s.claudeConnected, profileComplete: seeded, templateChosen: s.templateChosen, setupDismissed: s.setupDismissed });
  },
  setTemplateChosen: (chosen) => {
    set({ templateChosen: chosen });
    const s = get();
    persistSetup({ claudeConnected: s.claudeConnected, profileComplete: s.profileComplete, templateChosen: chosen, setupDismissed: s.setupDismissed });
  },
  setCurrentStep: (step) => set({ currentStep: step }),
  dismissSetup: () => {
    set({ setupDismissed: true });
    const s = get();
    persistSetup({ claudeConnected: s.claudeConnected, profileComplete: s.profileComplete, templateChosen: s.templateChosen, setupDismissed: true });
  },
  isSetupComplete: () => {
    const s = get();
    return s.claudeConnected && s.profileComplete;
  },
}));
