import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { useState, useRef, useEffect } from "react";
import { BookText, PhoneForwarded, DollarSign, Handshake, Briefcase, Settings, Plug, Menu, ChevronRight, BarChart2 } from "lucide-react";
import { cn } from "@/shared/lib/utils";
import { useAppStore } from "@/shared/stores/app-store";

const ALL_TABS = [
  { to: "/narrative",    icon: BookText,       label: "Business" },
  { to: "/admin",        icon: Settings,       label: "Admin" },
  { to: "/sales",        icon: Handshake,      label: "Sales" },
  { to: "/operations",   icon: Briefcase,      label: "Operations" },
  { to: "/billing",      icon: DollarSign,     label: "Billing" },
  { to: "/marketing",    icon: PhoneForwarded, label: "Marketing" },
  { to: "/reports",      icon: BarChart2,      label: "Reports" },
  { to: "/connections",  icon: Plug,           label: "Connections" },
];

export function MainTabs() {
  const location = useLocation();
  const navigate = useNavigate();
  const allowedTabs = useAppStore((s) => s.allowedTabs);
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  const visibleTabs = allowedTabs === null
    ? ALL_TABS
    : ALL_TABS.filter((t) => allowedTabs.includes(t.to));

  const activeTab = visibleTabs.find((t) => location.pathname.startsWith(t.to));

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    if (open) document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  return (
    <nav className="border-b border-border bg-card">
      <div className="px-4 py-2 flex items-center gap-3" ref={menuRef}>
        {/* Hamburger trigger */}
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className={cn(
            "flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
            open ? "bg-muted text-foreground" : "text-muted-foreground hover:bg-muted hover:text-foreground",
          )}
        >
          <Menu size={16} />
          <span className="hidden sm:inline">{activeTab?.label ?? "Menu"}</span>
        </button>

        {/* Active page breadcrumb (shows on mobile where label is hidden) */}
        {activeTab && (
          <div className="sm:hidden flex items-center gap-1.5 text-sm font-medium text-foreground">
            <activeTab.icon className="h-4 w-4 text-muted-foreground" />
            <span>{activeTab.label}</span>
          </div>
        )}

        {/* Dropdown */}
        {open && (
          <div className="absolute left-4 top-[57px] z-50 w-52 rounded-xl border border-border bg-card shadow-lg overflow-hidden">
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
    </nav>
  );
}
