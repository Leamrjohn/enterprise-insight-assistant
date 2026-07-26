import type { AssistantDataSource, CompanyMember, Conversation, ConversationMessage, CurrentUser, DataSource, DocumentItem, Snapshot, Task } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "/api";

const messageMap: Record<string, string> = {
  "invalid or missing API key": "API Key 无效或未提供。",
  "account is inactive": "当前账户已被禁用。",
  "administrator permission required": "此操作需要管理员权限。",
  "analysis permission required": "当前用户没有发起经营分析的权限。",
  "data source not found": "未找到数据源。",
  "schema snapshot not found": "未找到契约快照。",
  "conversation not found": "未找到会话。",
  "task not found": "未找到分析任务。",
};

export class ApiError extends Error { constructor(public status: number, message: string) { super(message); } }

export class ApiClient {
  constructor(private readonly accessToken: string) {}

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${this.accessToken}`, ...init.headers },
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      const message = payload.message ?? payload.detail ?? "请求失败，请稍后重试。";
      throw new ApiError(response.status, messageMap[message] ?? message);
    }
    return response.json() as Promise<T>;
  }

  me = () => this.request<CurrentUser>("/auth/me");
  updateMe = (name: string) => this.request<CurrentUser>("/auth/me", { method: "PATCH", body: JSON.stringify({ name }) });
  changePassword = (current_password: string, new_password: string) => this.request<void>("/auth/me/password", { method: "POST", body: JSON.stringify({ current_password, new_password }) });
  logout = () => this.request<void>("/auth/logout", { method: "POST" });
  dataSources = () => this.request<DataSource[]>("/company/data-sources");
  assistantDataSources = () => this.request<AssistantDataSource[]>("/company/assistant-data-sources");
  documents = () => this.request<DocumentItem[]>("/documents");
  conversations = () => this.request<Conversation[]>("/conversations");
  createConversation = (data_source_id: number, title?: string) => this.request<Conversation>("/conversations", { method: "POST", body: JSON.stringify({ data_source_id, title }) });
  messages = (conversationId: number) => this.request<ConversationMessage[]>(`/conversations/${conversationId}/messages`);
  sendMessage = (conversationId: number, content: string, document_ids: number[]) => this.request<{ task_id: number }>(`/conversations/${conversationId}/messages`, { method: "POST", body: JSON.stringify({ content, document_ids }) });
  task = (conversationId: number, taskId: number) => this.request<Task>(`/conversations/${conversationId}/tasks/${taskId}`);
  cancelTask = (conversationId: number, taskId: number) => this.request<Task>(`/conversations/${conversationId}/tasks/${taskId}/cancel`, { method: "POST" });
  snapshots = (sourceId: number) => this.request<Snapshot[]>(`/company/data-sources/${sourceId}/schema-snapshots`);
  discover = (sourceId: number) => this.request<Snapshot>(`/company/data-sources/${sourceId}/discover-schema`, { method: "POST" });
  activateSnapshot = (sourceId: number, snapshotId: number) => this.request<Snapshot>(`/company/data-sources/${sourceId}/schema-snapshots/${snapshotId}/activate`, { method: "POST" });
  createDataSource = (payload: object) => this.request<DataSource>("/company/data-sources", { method: "POST", body: JSON.stringify(payload) });
  members = () => this.request<CompanyMember[]>("/company/members");
  updateMember = (memberId: number, payload: object) => this.request<CompanyMember>(`/company/members/${memberId}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export async function login(username: string, password: string): Promise<{ access_token: string; expires_in: number }> {
  const response = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    const message = payload.message ?? payload.detail ?? "登录失败，请稍后重试。";
    throw new ApiError(response.status, messageMap[message] ?? message);
  }
  return response.json() as Promise<{ access_token: string; expires_in: number }>;
}
