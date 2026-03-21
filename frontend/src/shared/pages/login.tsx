import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Loader2, AlertCircle } from "lucide-react";

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
      {/* Header */}
      <div className="text-center lg:text-left">
        <p className="mb-4 text-sm font-semibold tracking-wide text-primary lg:hidden">
          SAPPHIRE
        </p>
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
