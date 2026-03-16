import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2, AlertCircle } from "lucide-react";

import { useAppStore } from "@/shared/stores/app-store";
import { register as registerUser } from "@/shared/api/auth";
import { registerSchema, type RegisterInput } from "@/shared/types/auth-schemas";

import { AuthLayout } from "@/shared/components/auth/auth-layout";
import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { PasswordInput } from "@/shared/components/ui/password-input";
import { PasswordStrength } from "@/shared/components/auth/password-strength";

export default function RegisterPage() {
  const navigate = useNavigate();
  const setTokens = useAppStore((s) => s.setTokens);
  const [apiError, setApiError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const {
    register: field,
    handleSubmit,
    watch,
    formState: { errors },
  } = useForm<RegisterInput>({
    resolver: zodResolver(registerSchema),
    mode: "onBlur",
  });

  const password = watch("password", "");

  const onSubmit = async (data: RegisterInput) => {
    setApiError("");
    setIsLoading(true);
    try {
      const res = await registerUser({
        email: data.email,
        password: data.password,
        full_name: data.full_name,
      });
      setTokens(res.access_token, res.refresh_token);
      navigate("/dashboard");
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      setApiError(detail || "Registration failed. Please try again.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <AuthLayout>
      {/* Header */}
      <div className="text-center lg:text-left">
        <p className="mb-4 text-sm font-semibold tracking-wide text-primary lg:hidden">
          WORKFORCE
        </p>
        <h1 className="text-2xl font-bold sm:text-3xl">Create your account</h1>
        <p className="mt-2 text-muted-foreground">
          Get started with AI-powered department automation
        </p>
      </div>

      {/* Form */}
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-5">
        {/* API error banner */}
        {apiError && (
          <div className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
            <AlertCircle size={16} className="shrink-0" />
            {apiError}
          </div>
        )}

        {/* Full Name */}
        <div className="space-y-1.5">
          <label htmlFor="full_name" className="block text-sm font-medium">
            Full Name
          </label>
          <Input
            id="full_name"
            type="text"
            autoComplete="name"
            placeholder="Jane Smith"
            {...field("full_name")}
          />
          {errors.full_name && (
            <p className="flex items-center gap-1 text-xs text-destructive">
              <AlertCircle size={12} />
              {errors.full_name.message}
            </p>
          )}
        </div>

        {/* Email */}
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

        {/* Password */}
        <div className="space-y-1.5">
          <label htmlFor="password" className="block text-sm font-medium">
            Password
          </label>
          <PasswordInput
            id="password"
            autoComplete="new-password"
            placeholder="••••••••"
            {...field("password")}
          />
          <PasswordStrength password={password} />
          {errors.password && (
            <p className="flex items-center gap-1 text-xs text-destructive">
              <AlertCircle size={12} />
              {errors.password.message}
            </p>
          )}
        </div>

        {/* Confirm Password */}
        <div className="space-y-1.5">
          <label htmlFor="confirmPassword" className="block text-sm font-medium">
            Confirm Password
          </label>
          <PasswordInput
            id="confirmPassword"
            autoComplete="new-password"
            placeholder="••••••••"
            {...field("confirmPassword")}
          />
          {errors.confirmPassword && (
            <p className="flex items-center gap-1 text-xs text-destructive">
              <AlertCircle size={12} />
              {errors.confirmPassword.message}
            </p>
          )}
        </div>

        {/* Submit */}
        <Button type="submit" className="w-full" disabled={isLoading}>
          {isLoading ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              Creating account...
            </>
          ) : (
            "Create account"
          )}
        </Button>
      </form>

      {/* Switch to login */}
      <p className="text-center text-sm text-muted-foreground">
        Already have an account?{" "}
        <Link to="/login" className="font-medium text-primary hover:underline">
          Sign in
        </Link>
      </p>
    </AuthLayout>
  );
}
