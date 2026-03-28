import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { useAppStore } from "@/shared/stores/app-store";
import client from "@/shared/api/client";
import type { TokenResponse } from "@/shared/types/auth";

/**
 * Handles the post-Azure AD redirect.
 *
 * Microsoft redirects the browser to this frontend route with ?code=...&state=...
 * SWA serves index.html (SPA navigation), React renders this component, which
 * makes a fetch call to /api/v1/auth/microsoft/exchange to do the code exchange
 * on the backend. This avoids SWA's navigationFallback intercepting an /api/ URL.
 */
export default function AuthCallbackPage() {
  const navigate = useNavigate();
  const setTokens = useAppStore((s) => s.setTokens);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const code = params.get("code");
    const error = params.get("error");

    if (error || !code) {
      navigate("/login?error=auth_failed", { replace: true });
      return;
    }

    client
      .get<TokenResponse>("/auth/microsoft/exchange", { params: { code, state: params.get("state") ?? "" } })
      .then(({ data }) => {
        setTokens(data.access_token, data.refresh_token);
        navigate("/dashboard", { replace: true });
      })
      .catch(() => {
        navigate("/login?error=auth_failed", { replace: true });
      });
  }, []);

  return (
    <div className="flex h-screen items-center justify-center">
      <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
    </div>
  );
}
