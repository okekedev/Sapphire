/**
 * Notification Bell — Topbar component with dropdown.
 *
 * Shows an unread count badge and a dropdown list of recent notifications.
 * Polls every 30 seconds for new notifications.
 */

import { useState, useEffect, useRef, useCallback } from "react";
import { Bell, CheckCircle2, AlertCircle, PauseCircle, Loader2, Check } from "lucide-react";
import { Button } from "@/shared/components/ui/button";
import { useAppStore } from "@/shared/stores/app-store";
import {
  listNotifications,
  markNotificationRead,
  markAllNotificationsRead,
  type NotificationItem,
} from "@/shared/api/notifications";

const ICON_MAP: Record<string, typeof CheckCircle2> = {
  info: CheckCircle2,
  error: AlertCircle,
};

const COLOR_MAP: Record<string, string> = {
  info: "text-blue-500",
  error: "text-red-500",
};

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

export function NotificationBell() {
  const businessId = useAppStore((s) => s.activeBusiness?.id ?? "");
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [unread, setUnread] = useState(0);
  const [loading, setLoading] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const fetchNotifications = useCallback(async () => {
    if (!businessId) return;
    try {
      const data = await listNotifications(businessId, { limit: 20 });
      setItems(data.notifications);
      setUnread(data.unread_count);
    } catch {
      // Silently fail — notifications are non-critical
    }
  }, [businessId]);

  // Initial fetch + polling
  useEffect(() => {
    fetchNotifications();
    const interval = setInterval(fetchNotifications, 30000);
    return () => clearInterval(interval);
  }, [fetchNotifications]);

  // Close on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    if (open) document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const handleMarkRead = async (id: string) => {
    try {
      await markNotificationRead(id);
      setItems((prev) =>
        prev.map((n) => (n.id === id ? { ...n, is_read: true } : n)),
      );
      setUnread((prev) => Math.max(0, prev - 1));
    } catch {
      // ignore
    }
  };

  const handleMarkAllRead = async () => {
    if (!businessId) return;
    setLoading(true);
    try {
      await markAllNotificationsRead(businessId);
      setItems((prev) => prev.map((n) => ({ ...n, is_read: true })));
      setUnread(0);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="relative" ref={dropdownRef}>
      <Button
        variant="ghost"
        size="icon"
        onClick={() => setOpen(!open)}
        title="Notifications"
        className="relative"
      >
        <Bell className="h-4 w-4" />
        {unread > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-bold text-white">
            {unread > 99 ? "99+" : unread}
          </span>
        )}
      </Button>

      {open && (
        <div className="absolute right-0 top-full z-50 mt-2 w-80 rounded-lg border border-border bg-card shadow-lg">
          {/* Header */}
          <div className="flex items-center justify-between border-b border-border px-4 py-2.5">
            <span className="text-sm font-semibold">Notifications</span>
            {unread > 0 && (
              <button
                onClick={handleMarkAllRead}
                disabled={loading}
                className="flex items-center gap-1 text-[11px] text-primary hover:underline disabled:opacity-50"
              >
                <Check className="h-3 w-3" />
                Mark all read
              </button>
            )}
          </div>

          {/* List */}
          <div className="max-h-80 overflow-y-auto">
            {items.length === 0 ? (
              <div className="px-4 py-8 text-center text-xs text-muted-foreground">
                No notifications yet
              </div>
            ) : (
              items.map((item) => {
                const Icon = ICON_MAP[item.type] ?? Bell;
                const color = COLOR_MAP[item.type] ?? "text-muted-foreground";

                return (
                  <button
                    key={item.id}
                    onClick={() => !item.is_read && handleMarkRead(item.id)}
                    className={`flex w-full items-start gap-3 px-4 py-3 text-left transition-colors hover:bg-muted/50 ${
                      !item.is_read ? "bg-primary/5" : ""
                    }`}
                  >
                    <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${color}`} />
                    <div className="min-w-0 flex-1">
                      <p className={`text-xs leading-snug ${!item.is_read ? "font-medium" : "text-muted-foreground"}`}>
                        {item.title}
                      </p>
                      <p className="mt-0.5 truncate text-[10px] text-muted-foreground">
                        {item.message}
                      </p>
                      <p className="mt-1 text-[10px] text-muted-foreground/60">
                        {timeAgo(item.created_at)}
                      </p>
                    </div>
                    {!item.is_read && (
                      <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-primary" />
                    )}
                  </button>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
}
