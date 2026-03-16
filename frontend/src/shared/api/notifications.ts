/**
 * Notifications API — stub for notification bell component.
 */
import client from "./client";

export interface NotificationItem {
  id: string;
  business_id: string;
  type: string;
  title: string;
  message: string | null;
  is_read: boolean;
  metadata: Record<string, unknown> | null;
  created_at: string;
}

export interface NotificationsResponse {
  notifications: NotificationItem[];
  total: number;
  unread_count: number;
}

export async function listNotifications(
  businessId: string,
  params?: { unread_only?: boolean; limit?: number },
): Promise<NotificationsResponse> {
  const res = await client.get("/notifications", {
    params: { business_id: businessId, ...params },
  });
  return res.data;
}

export async function markNotificationRead(
  businessId: string,
  notificationId: string,
): Promise<void> {
  await client.patch(`/notifications/${notificationId}/read`, null, {
    params: { business_id: businessId },
  });
}

export async function markAllNotificationsRead(
  businessId: string,
): Promise<void> {
  await client.patch("/notifications/read-all", null, {
    params: { business_id: businessId },
  });
}
