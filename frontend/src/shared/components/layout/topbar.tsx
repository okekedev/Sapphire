import { useNavigate } from "react-router-dom";
import { LogOut } from "lucide-react";
import { useAppStore } from "@/shared/stores/app-store";
import { Button } from "@/shared/components/ui/button";
import { BusinessSwitcher } from "./business-switcher";
import { NotificationBell } from "./notification-bell";
import { ThemeToggle } from "./theme-toggle";

export function Topbar() {
  const { logout } = useAppStore();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-border bg-card px-6">
      <div className="flex items-center gap-4">
        <BusinessSwitcher />
      </div>

      <span className="text-sm font-bold tracking-tight">Workforce</span>

      <div className="flex items-center gap-3">
        <NotificationBell />
        <ThemeToggle />
        <Button variant="ghost" size="icon" onClick={handleLogout} title="Sign out">
          <LogOut className="h-4 w-4" />
        </Button>
      </div>
    </header>
  );
}
