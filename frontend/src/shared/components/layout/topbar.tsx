import { useNavigate, useLocation } from "react-router-dom";
import { useState, useRef, useEffect } from "react";
import { LogOut, Zap, Menu, ChevronRight, BookText, PhoneForwarded, DollarSign, Handshake, Briefcase, Settings, Plug, BarChart2, Users, Building2, LayoutDashboard, ChevronsUpDown, Check, Plus, X } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useAppStore } from "@/shared/stores/app-store";
import { usePermissions } from "@/shared/hooks/use-permissions";
import { listBusinesses } from "@/shared/api/businesses";
import { Button } from "@/shared/components/ui/button";
import { ThemeToggle } from "./theme-toggle";
import { cn } from "@/shared/lib/utils";

// permission = null means always visible (dashboard, connections, narrative are unrestricted)
const MAIN_TABS = [
  { to: "/dashboard",     icon: LayoutDashboard, label: "Dashboard",     permission: null },
  { to: "/sales",         icon: Handshake,       label: "Sales",         permission: "access_sales" },
  { to: "/contacts",      icon: Users,           label: "Contacts",      permission: "access_contacts" },
  { to: "/organizations", icon: Building2,       label: "Organizations", permission: "access_contacts" },
  { to: "/jobs",          icon: Briefcase,       label: "Jobs",          permission: "access_operations" },
  { to: "/marketing",     icon: PhoneForwarded,  label: "Marketing",     permission: "access_marketing" },
  { to: "/reports",       icon: BarChart2,       label: "Reports",       permission: "access_reports" },
];

const SETTINGS_TABS = [
  { to: "/billing",     icon: DollarSign, label: "Billing",     permission: "access_billing" },
  { to: "/connections", icon: Plug,       label: "Connections", permission: null },
  { to: "/narrative",   icon: BookText,   label: "Business",    permission: "manage_business" },
  { to: "/admin",       icon: Settings,   label: "Admin",       permission: "access_admin" },
];

export function Topbar() {
  const { logout, activeBusiness, setActiveBusiness } = useAppStore();
  const { can, isGlobalAdmin } = usePermissions();
  const navigate = useNavigate();
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const [clientOpen, setClientOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const clientRef = useRef<HTMLDivElement>(null);

  const { data: businesses = [] } = useQuery({
    queryKey: ["businesses"],
    queryFn: listBusinesses,
  });

  const visibleMain = MAIN_TABS.filter((t) => t.permission === null || can(t.permission));
  const visibleSettings = SETTINGS_TABS.filter((t) => t.permission === null || can(t.permission));

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false);
      if (clientRef.current && !clientRef.current.contains(e.target as Node)) setClientOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  const renderNavItem = (to: string, Icon: React.ElementType, label: string) => {
    const isActive = location.pathname === to || (to !== "/" && location.pathname.startsWith(to + "/"));
    return (
      <button
        key={to}
        type="button"
        onClick={() => { navigate(to); setMenuOpen(false); }}
        className={cn(
          "w-full flex items-center gap-3 px-4 py-2.5 text-sm transition-colors text-left",
          isActive ? "bg-primary/8 text-primary font-medium" : "text-foreground hover:bg-muted",
        )}
      >
        <Icon className="h-4 w-4 shrink-0 text-muted-foreground" />
        <span className="flex-1">{label}</span>
        {isActive && <ChevronRight size={13} className="text-primary" />}
      </button>
    );
  };

  return (
    <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-border bg-card px-6">
      {/* Logo */}
      <div className="flex items-center gap-3">
        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary">
          <Zap size={14} className="text-primary-foreground" fill="currentColor" />
        </div>
        <span className="hidden text-sm font-bold tracking-tight sm:block">Sapphire</span>

        {/* Client switcher */}
        {businesses.length > 0 && (
          <div ref={clientRef} className="relative">
            <button
              type="button"
              onClick={() => setClientOpen((v) => !v)}
              className="flex items-center gap-1.5 rounded-lg border border-border bg-muted/50 px-2.5 py-1.5 text-xs font-medium text-foreground hover:bg-muted transition-colors max-w-[160px]"
            >
              <span className="truncate">{activeBusiness?.name ?? "Select client"}</span>
              <ChevronsUpDown size={12} className="shrink-0 text-muted-foreground" />
            </button>

            {clientOpen && (
              <div className="absolute left-0 top-full z-50 mt-1 w-56 rounded-xl border border-border bg-card shadow-lg overflow-hidden">
                <div className="px-3 py-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground border-b border-border">
                  Clients
                </div>
                {businesses.map((biz) => (
                  <button
                    key={biz.id}
                    type="button"
                    onClick={() => { setActiveBusiness(biz); setClientOpen(false); navigate("/dashboard"); }}
                    className="w-full flex items-center gap-2 px-3 py-2 text-sm text-left hover:bg-muted transition-colors"
                  >
                    <Check size={13} className={cn("shrink-0", activeBusiness?.id === biz.id ? "text-primary" : "text-transparent")} />
                    <span className="truncate">{biz.name}</span>
                  </button>
                ))}
                {isGlobalAdmin && (
                  <>
                    <div className="border-t border-border" />
                    <button
                      type="button"
                      onClick={() => { setClientOpen(false); navigate("/clients/new"); }}
                      className="w-full flex items-center gap-2 px-3 py-2 text-sm text-left text-muted-foreground hover:bg-muted transition-colors"
                    >
                      <Plus size={13} className="shrink-0" />
                      Add client
                    </button>
                  </>
                )}
              </div>
            )}
          </div>
        )}
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
            onClick={() => setMenuOpen((v) => !v)}
            className={cn(
              "flex items-center justify-center h-8 w-8 rounded-lg transition-colors",
              menuOpen ? "bg-muted text-foreground" : "text-muted-foreground hover:bg-muted hover:text-foreground",
            )}
            title="Menu"
          >
            <Menu size={16} />
          </button>

          {menuOpen && (
            <>
              {/* Backdrop on mobile */}
              <div
                className="fixed inset-0 z-40 bg-black/30 md:hidden"
                onClick={() => setMenuOpen(false)}
              />
              {/* Desktop: dropdown; Mobile: full-height slide-in from right */}
              <div className={cn(
                "z-50 bg-card border-border overflow-y-auto",
                // Mobile: full-height slide-in from right
                "fixed top-0 right-0 bottom-0 w-64 border-l shadow-xl",
                // Desktop: dropdown below the button (must reset bottom-0 or element collapses to zero height)
                "md:absolute md:top-full md:bottom-auto md:right-0 md:mt-1 md:w-52 md:border md:rounded-xl md:shadow-lg md:max-h-[calc(100vh-4.5rem)]",
              )}>
                {/* Mobile header */}
                <div className="flex items-center justify-between border-b border-border px-4 py-3 md:hidden">
                  <span className="text-sm font-semibold">Navigation</span>
                  <button type="button" onClick={() => setMenuOpen(false)} className="text-muted-foreground hover:text-foreground">
                    <X size={16} />
                  </button>
                </div>

                {/* Main nav */}
                {visibleMain.map(({ to, icon, label }) => renderNavItem(to, icon, label))}

                {/* Settings section */}
                {visibleSettings.length > 0 && (
                  <>
                    <div className="mx-3 my-1 border-t border-border" />
                    <p className="px-4 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                      Settings
                    </p>
                    {visibleSettings.map(({ to, icon, label }) => renderNavItem(to, icon, label))}
                  </>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
