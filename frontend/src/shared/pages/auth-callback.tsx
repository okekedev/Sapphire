import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { useAppStore } from "@/shared/stores/app-store";

/**
 * Handles the post-Azure AD redirect.
 * Azure AD → backend → frontend/auth/callback#access_token=...&refresh_token=...
 */
export default function AuthCallbackPage() {
  const navigate = useNavigate();
  const setTokens = useAppStore((s) => s.setTokens);

  useEffect(() => {
    const hash = window.location.hash.slice(1); // strip leading #
    const params = new URLSearchParams(hash);
    const accessToken = params.get("access_token");
    const refreshToken = params.get("refresh_token");

    if (accessToken && refreshToken) {
      setTokens(accessToken, refreshToken);
      navigate("/dashboard", { replace: true });
    } else {
      navigate("/login?error=auth_failed", { replace: true });
    }
  }, []);

  return (
    <div className="flex h-screen items-center justify-center">
      <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
    </div>
  );
}
