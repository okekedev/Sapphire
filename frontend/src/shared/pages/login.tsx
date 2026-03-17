import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2, AlertCircle } from "lucide-react";

import { useAppStore } from "@/shared/stores/app-store";
import { login, getMicrosoftLoginUrl } from "@/shared/api/auth";
import { loginSchema, type LoginInput } from "@/shared/types/auth-schemas";

import { AuthLayout } from "@/shared/components/auth/auth-layout";
import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { PasswordInput } from "@/shared/components/ui/password-input";

export default function LoginPage() {
  const navigate = useNavigate();
  const setTokens = useAppStore((s) => s.setTokens);
  const [apiError, setApiError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isMsLoading, setIsMsLoading] = useState(false);

  const {
    register: field,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginInput>({
    resolver: zodResolver(loginSchema),
    mode: "onBlur",
  });

  const onSubmit = async (data: LoginInput) => {
    setApiError("");
    setIsLoading(true);
    try {
      const res = await login(data);
      setTokens(res.access_token, res.refresh_token);
      navigate("/dashboard");
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      setApiError(detail || "Invalid email or password");
    } finally {
      setIsLoading(false);
    }
  };

  const onMicrosoftLogin = async () => {
    setApiError("");
    setIsMsLoading(true);
    try {
      const authUrl = await getMicrosoftLoginUrl();
      window.location.href = authUrl;
    } catch (err: any) {
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

      {/* Microsoft SSO — primary */}
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

      {/* Divider */}
      <div className="relative">
        <div className="absolute inset-0 flex items-center">
          <span className="w-full border-t" />
        </div>
        <div className="relative flex justify-center text-xs uppercase">
          <span className="bg-background px-2 text-muted-foreground">or</span>
        </div>
      </div>

      {/* Email / password fallback */}
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
        <div className="space-y-1.5">
          <label htmlFor="email" className="block text-sm font-medium">
            Email
          </label>
          <Input
            id="email"
            type="email"
            autoComplete="email"
            placeholder="you@example.com"
            {...field("email")}
          />
          {errors.email && (
            <p className="flex items-center gap-1 text-xs text-destructive">
              <AlertCircle size={12} />
              {errors.email.message}
            </p>
          )}
        </div>

        <div className="space-y-1.5">
          <label htmlFor="password" className="block text-sm font-medium">
            Password
          </label>
          <PasswordInput
            id="password"
            autoComplete="current-password"
            placeholder="••••••••"
            {...field("password")}
          />
          {errors.password && (
            <p className="flex items-center gap-1 text-xs text-destructive">
              <AlertCircle size={12} />
              {errors.password.message}
            </p>
          )}
        </div>

        <Button type="submit" className="w-full" disabled={isLoading} variant="ghost">
          {isLoading ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              Signing in...
            </>
          ) : (
            "Sign in with email"
          )}
        </Button>
      </form>
    </AuthLayout>
  );
}
