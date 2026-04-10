import { useNavigate, useLocation } from "react-router-dom";
import { useState, useRef, useEffect } from "react";
import { LogOut, Zap, Menu, ChevronRight, BookText, PhoneForwarded, DollarSign, Handshake, Briefcase, Settings, Plug, BarChart2 } from "lucide-react";
import { useAppStore } from "@/shared/stores/app-store";
import { Button } from "@/shared/components/ui/button";
import { ThemeToggle } from "./theme-toggle";
import { cn } from "@/shared/lib/utils";

const ALL_TABS = [
  { to: "/narrative",   icon: BookText,       label: "Business" },
  { to: "/admin",       icon: Settings,       label: "Admin" },
  { to: "/sales",       icon: Handshake,      label: "Sales" },
  { to: "/operations",  icon: Briefcase,      label: "Operations" },
  { to: "/billing",     icon: DollarSign,     label: "Billing" },
  { to: "/marketing",   icon: PhoneForwarded, label: "Marketing" },
  { to: "/reports",     icon: BarChart2,      label: "Reports" },
  { to: "/connections", icon: Plug,           label: "Connections" },
];

export function Topbar() {
  const { logout, allowedTabs } = useAppStore();
  const navigate = useNavigate();
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  const visibleTabs = allowedTabs === null
    ? ALL_TABS
    : ALL_TABS.filter((t) => allowedTabs.includes(t.to));

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    if (open) document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-border bg-card px-6">
      {/* Logo */}
      <div className="flex items-center gap-2">
        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary">
          <Zap size={14} className="text-primary-foreground" fill="currentColor" />
        </div>
        <span className="text-sm font-bold tracking-tight">Sapphire</span>
      </div>

      <div className="flex items-center gap-2">
        <ThemeToggle />
        <Button variant="ghost" size="icon" onClick={handleLogout} title="Sign out">
          <LogOut className="h-4 w-4" />
        </Button>

        {/* Nav hamburger */}
        <div ref={menuRef} className="relative">
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            className={cn(
              "flex items-center justify-center h-8 w-8 rounded-lg transition-colors",
              open ? "bg-muted text-foreground" : "text-muted-foreground hover:bg-muted hover:text-foreground",
            )}
            title="Menu"
          >
            <Menu size={16} />
          </button>

          {open && (
            <div className="absolute right-0 top-full z-50 mt-1 w-52 rounded-xl border border-border bg-card shadow-lg overflow-hidden">
              {visibleTabs.map(({ to, icon: Icon, label }) => {
                const isActive = location.pathname.startsWith(to);
                return (
                  <button
                    key={to}
                    type="button"
                    onClick={() => { navigate(to); setOpen(false); }}
                    className={cn(
                      "w-full flex items-center gap-3 px-4 py-2.5 text-sm transition-colors text-left",
                      isActive
                        ? "bg-primary/8 text-primary font-medium"
                        : "text-foreground hover:bg-muted",
                    )}
                  >
                    <Icon className="h-4 w-4 shrink-0 text-muted-foreground" />
                    <span className="flex-1">{label}</span>
                    {isActive && <ChevronRight size={13} className="text-primary" />}
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
