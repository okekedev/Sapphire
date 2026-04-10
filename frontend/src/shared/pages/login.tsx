import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Loader2, AlertCircle, Building2 } from "lucide-react";

import { useAppStore } from "@/shared/stores/app-store";
import { getMicrosoftLoginUrl } from "@/shared/api/auth";

import { AuthLayout } from "@/shared/components/auth/auth-layout";
import { Button } from "@/shared/components/ui/button";

export default function LoginPage() {
  const navigate = useNavigate();
  const [apiError, setApiError] = useState("");
  const [isMsLoading, setIsMsLoading] = useState(false);

  // suppress unused warning — navigate kept for future post-login redirect use
  void navigate;

  const onMicrosoftLogin = async () => {
    setApiError("");
    setIsMsLoading(true);
    try {
      const authUrl = await getMicrosoftLoginUrl();
      window.location.href = authUrl;
    } catch {
      setApiError("Could not reach authentication server");
      setIsMsLoading(false);
    }
  };

  return (
    <AuthLayout>
      {/* Logo + brand */}
      <div className="flex flex-col items-center gap-3">
        <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-primary">
          <Building2 className="h-6 w-6 text-primary-foreground" />
        </div>
        <p className="text-xs font-semibold tracking-widest text-primary uppercase">Sapphire</p>
      </div>

      {/* Header */}
      <div className="text-center">
        <h1 className="text-2xl font-bold sm:text-3xl">Welcome back</h1>
        <p className="mt-2 text-muted-foreground">Sign in to continue</p>
      </div>

      {/* Error banner */}
      {apiError && (
        <div className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
          <AlertCircle size={16} className="shrink-0" />
          {apiError}
        </div>
      )}

      {/* Microsoft SSO — only sign-in method */}
      <Button
        type="button"
        variant="outline"
        className="w-full gap-2"
        onClick={onMicrosoftLogin}
        disabled={isMsLoading}
      >
        {isMsLoading ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <svg viewBox="0 0 21 21" className="h-4 w-4" fill="none">
            <rect x="1" y="1" width="9" height="9" fill="#F25022" />
            <rect x="11" y="1" width="9" height="9" fill="#7FBA00" />
            <rect x="1" y="11" width="9" height="9" fill="#00A4EF" />
            <rect x="11" y="11" width="9" height="9" fill="#FFB900" />
          </svg>
        )}
        Sign in with Microsoft
      </Button>
    </AuthLayout>
  );
}
