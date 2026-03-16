import { NavLink, useLocation } from "react-router-dom";
import { Home, PhoneForwarded, DollarSign, Handshake, Briefcase, Settings, Monitor } from "lucide-react";
import { cn } from "@/shared/lib/utils";
import { useAppStore } from "@/shared/stores/app-store";

/** Core workflow tabs — the main business flow */
const CORE_TABS = [
  { to: "/dashboard",    icon: Home,             label: "Home" },
  { to: "/admin",        icon: Settings,         label: "Admin" },
  { to: "/sales",        icon: Handshake,        label: "Sales" },
  { to: "/operations",   icon: Briefcase,        label: "Operations" },
  { to: "/billing",      icon: DollarSign,       label: "Billing" },
];

/** Utility / extra tabs — not part of the main workflow */
const EXTRA_TABS = [
  { to: "/marketing",    icon: PhoneForwarded,   label: "Marketing" },
  { to: "/it",           icon: Monitor,          label: "IT" },
];

const ALL_TABS = [...CORE_TABS, ...EXTRA_TABS];

export function MainTabs() {
  const location = useLocation();
  const allowedTabs = useAppStore((s) => s.allowedTabs);

  // null = owner / all-access; string[] = only show those tabs
  const visibleTabs = allowedTabs === null
    ? ALL_TABS
    : ALL_TABS.filter((t) => allowedTabs.includes(t.to));

  const extraPaths = new Set(EXTRA_TABS.map((t) => t.to));
  const visibleCore = visibleTabs.filter((t) => !extraPaths.has(t.to));
  const visibleExtra = visibleTabs.filter((t) => extraPaths.has(t.to));

  return (
    <nav className="border-b border-border bg-card">
      <div className="flex items-center gap-1 px-6">
        {visibleCore.map(({ to, icon: Icon, label }) => {
          const isActive = location.pathname.startsWith(to);
          return (
            <NavLink
              key={to}
              to={to}
              className={cn(
                "flex items-center gap-2 border-b-2 px-4 py-3 text-sm font-medium transition-colors",
                isActive
                  ? "border-foreground text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground",
              )}
            >
              <Icon className="h-4 w-4" />
              <span>{label}</span>
            </NavLink>
          );
        })}

        {visibleExtra.length > 0 && (
          <>
            <div className="mx-1 h-5 w-px bg-border/60" />
            {visibleExtra.map(({ to, icon: Icon, label }) => {
              const isActive = location.pathname.startsWith(to);
              return (
                <NavLink
                  key={to}
                  to={to}
                  className={cn(
                    "flex items-center gap-2 border-b-2 px-4 py-3 text-xs font-medium transition-colors",
                    isActive
                      ? "border-foreground/60 text-foreground"
                      : "border-transparent text-muted-foreground/60 hover:text-muted-foreground",
                  )}
                >
                  <Icon className="h-3.5 w-3.5" />
                  <span>{label}</span>
                </NavLink>
              );
            })}
          </>
        )}
      </div>
    </nav>
  );
}
