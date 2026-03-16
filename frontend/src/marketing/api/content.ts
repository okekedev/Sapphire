/**
 * Content Studio API — media upload, content post CRUD.
 */
import client from "./client";

// ── Types ──

export interface MediaFile {
  id: string;
  business_id: string;
  filename: string;
  file_path: string;
  mime_type: string;
  size_bytes: number;
  uploaded_by: string | null;
  created_at: string;
}

export interface MediaFileListResponse {
  files: MediaFile[];
  total: number;
}

export interface ContentPost {
  id: string;
  business_id: string;
  content: string;
  platform_targets: string[];
  media_ids: string[];
  status: "draft" | "posted" | "failed";
  posted_at: string | null;
  posted_by: string | null;
  platform_results: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface ContentPostListResponse {
  posts: ContentPost[];
  total: number;
}

export interface ContentPostCreate {
  content: string;
  platform_targets: string[];
  media_ids: string[];
}

export interface ContentPostUpdate {
  content?: string;
  platform_targets?: string[];
  media_ids?: string[];
}

// ── Media API ──

export async function uploadMedia(
  businessId: string,
  file: File,
): Promise<MediaFile> {
  const formData = new FormData();
  formData.append("file", file);
  const { data } = await client.post(
    `/marketing/media/upload?business_id=${businessId}`,
    formData,
    { headers: { "Content-Type": "multipart/form-data" } },
  );
  return data;
}

export async function listMedia(
  businessId: string,
  limit = 50,
  offset = 0,
): Promise<MediaFileListResponse> {
  const { data } = await client.get("/marketing/media", {
    params: { business_id: businessId, limit, offset },
  });
  return data;
}

export async function deleteMedia(
  businessId: string,
  mediaId: string,
): Promise<void> {
  await client.delete(`/marketing/media/${mediaId}`, {
    params: { business_id: businessId },
  });
}

export function mediaFileUrl(businessId: string, mediaId: string): string {
  return `/api/v1/marketing/media/${mediaId}/file?business_id=${businessId}`;
}

// ── Content Post API ──

export async function createPost(
  businessId: string,
  body: ContentPostCreate,
): Promise<ContentPost> {
  const { data } = await client.post(
    `/marketing/posts?business_id=${businessId}`,
    body,
  );
  return data;
}

export async function listPosts(
  businessId: string,
  status?: string,
  limit = 20,
  offset = 0,
): Promise<ContentPostListResponse> {
  const { data } = await client.get("/marketing/posts", {
    params: { business_id: businessId, status, limit, offset },
  });
  return data;
}

export async function updatePost(
  businessId: string,
  postId: string,
  body: ContentPostUpdate,
): Promise<ContentPost> {
  const { data } = await client.patch(
    `/marketing/posts/${postId}?business_id=${businessId}`,
    body,
  );
  return data;
}

export async function deletePost(
  businessId: string,
  postId: string,
): Promise<void> {
  await client.delete(`/marketing/posts/${postId}`, {
    params: { business_id: businessId },
  });
}

export async function publishPost(
  businessId: string,
  postId: string,
  employeeId?: string,
): Promise<ContentPost> {
  const { data } = await client.post(
    `/marketing/posts/${postId}/publish`,
    null,
    { params: { business_id: businessId, employee_id: employeeId } },
  );
  return data;
}
