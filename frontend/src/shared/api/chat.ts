import client from "./client";

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

// ── Assistant Chat (server-side system prompt, used by department chats) ──

export interface AssistantChatRequest {
  business_id: string;
  conversation_id?: string | null;
  messages: ChatMessage[];
  user_message: string;
}

export interface AssistantChatResponse {
  content: string;
  conversation_id?: string | null;
  error?: string | null;
  auth_error?: boolean;
  auth_error_type?: string | null; // "token_expired" | "not_connected"
}

export async function sendAssistantChat(
  payload: AssistantChatRequest
): Promise<AssistantChatResponse> {
  const res = await client.post("/chat", payload);
  return res.data;
}

// ── Conversation Management ──

export interface ConversationSummary {
  id: string;
  title?: string | null;
  status: string;
  source: "user_chat" | "department_chat";
  employee_id?: string | null;
  employee_name?: string | null;
  is_read: boolean;
  message_count: number;
  created_at: string;
  updated_at: string;
}

export interface ConversationMessageOut {
  id: string;
  role: "user" | "assistant";
  content: string;
  proposal?: Record<string, unknown> | null;
  delivery_content?: Record<string, unknown> | null;
  status: string;
  created_at: string;
}

export interface ConversationDetail extends ConversationSummary {
  messages: ConversationMessageOut[];
}

export async function listConversations(
  businessId: string,
  options?: { status?: string; source?: string; limit?: number; offset?: number }
): Promise<ConversationSummary[]> {
  const params: Record<string, string | number> = {
    business_id: businessId,
  };
  if (options?.status) params.status = options.status;
  if (options?.source) params.source = options.source;
  if (options?.limit) params.limit = options.limit;
  if (options?.offset) params.offset = options.offset;
  const res = await client.get("/chat/conversations", { params });
  return res.data;
}

export async function getConversation(
  conversationId: string
): Promise<ConversationDetail> {
  const res = await client.get(`/chat/conversations/${conversationId}`);
  return res.data;
}

export async function archiveConversation(
  conversationId: string
): Promise<void> {
  await client.delete(`/chat/conversations/${conversationId}`);
}

// ── Employee Chat (department heads) ──

export interface EmployeeChatRequest {
  business_id: string;
  employee_id: string;
  messages: ChatMessage[];
  user_message: string;
}

export interface ChatResponse {
  content: string;
  error?: string | null;
}

export async function sendEmployeeChat(payload: EmployeeChatRequest): Promise<ChatResponse> {
  const res = await client.post("/chat/employee", payload);
  return res.data;
}
