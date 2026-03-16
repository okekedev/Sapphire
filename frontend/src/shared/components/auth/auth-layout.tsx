import type { ReactNode } from "react";
import { Building2, Users, Zap, BarChart3 } from "lucide-react";

interface AuthLayoutProps {
  children: ReactNode;
}

export function AuthLayout({ children }: AuthLayoutProps) {
  return (
    <div className="flex min-h-screen">
      {/* Branded sidebar — hidden on mobile */}
      <div className="hidden lg:flex lg:w-1/2 flex-col justify-between bg-gradient-to-br from-primary/10 via-primary/5 to-background p-12">
        <div>
          {/* Logo / wordmark */}
          <div className="flex items-center gap-2">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary">
              <Building2 className="h-5 w-5 text-primary-foreground" />
            </div>
            <span className="text-2xl font-bold tracking-tight">Workforce</span>
          </div>
        </div>

        {/* Value proposition */}
        <div className="space-y-8">
          <div>
            <h2 className="text-3xl font-bold leading-tight">
              AI-powered teams,
              <br />
              working for you.
            </h2>
            <p className="mt-3 text-lg text-muted-foreground max-w-md">
              Automate your departments with intelligent AI employees that handle
              calls, emails, and tasks around the clock.
            </p>
          </div>

          {/* Feature highlights */}
          <div className="grid grid-cols-2 gap-4 max-w-md">
            <FeatureCard
              icon={<Users size={18} />}
              title="AI Employees"
              desc="Dedicated agents per department"
            />
            <FeatureCard
              icon={<Zap size={18} />}
              title="Automation"
              desc="Workflows that run themselves"
            />
            <FeatureCard
              icon={<BarChart3 size={18} />}
              title="Insights"
              desc="Real-time business analytics"
            />
            <FeatureCard
              icon={<Building2 size={18} />}
              title="Multi-dept"
              desc="Sales, marketing, finance & more"
            />
          </div>
        </div>

        {/* Footer */}
        <p className="text-xs text-muted-foreground">
          &copy; {new Date().getFullYear()} Workforce. All rights reserved.
        </p>
      </div>

      {/* Form area — full width on mobile, right half on desktop */}
      <div className="flex w-full lg:w-1/2 items-center justify-center px-4 py-12 sm:px-8">
        <div className="w-full max-w-md space-y-8">{children}</div>
      </div>
    </div>
  );
}

function FeatureCard({
  icon,
  title,
  desc,
}: {
  icon: ReactNode;
  title: string;
  desc: string;
}) {
  return (
    <div className="flex items-start gap-3 rounded-lg border border-border/50 bg-background/50 p-3">
      <div className="mt-0.5 text-primary">{icon}</div>
      <div>
        <p className="text-sm font-medium">{title}</p>
        <p className="text-xs text-muted-foreground">{desc}</p>
      </div>
    </div>
  );
}
