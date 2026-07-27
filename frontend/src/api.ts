import type { AssistantDataSource, CompanyInvitation, CompanyMember, Conversation, ConversationMessage, CreatedCompanyInvitation, CurrentUser, DataSource, DocumentChunk, DocumentItem, MembershipApplication, Snapshot, Task } from "./types";

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
  "account already has an application": "该账户已有待处理或历史申请，请勿重复提交。",
  "application is not pending": "该申请已被处理，请刷新列表后重试。",
  "platform already has a company": "平台已完成首个公司初始化，请使用邀请码申请加入。",
  "application cannot be resubmitted with this invitation": "无法使用该邀请码重新提交申请；请确认邀请码属于原公司且仍可使用。",
  "invitation code is invalid or unavailable": "邀请码无效、已过期或使用次数已耗尽。",
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
  documentChunks = (documentId: number) => this.request<DocumentChunk[]>(`/documents/${documentId}/chunks`);
  deleteDocument = (documentId: number) => this.request<DocumentItem>(`/documents/${documentId}`, { method: "DELETE" });
  async uploadDocument(file: File): Promise<DocumentItem> {
    const formData = new FormData();
    formData.append("file", file);
    const response = await fetch(`${API_BASE}/documents/upload`, { method: "POST", headers: { Authorization: `Bearer ${this.accessToken}` }, body: formData });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      const message = payload.message ?? payload.detail ?? "文档上传失败，请稍后重试。";
      throw new ApiError(response.status, messageMap[message] ?? message);
    }
    return response.json() as Promise<DocumentItem>;
  }
  conversations = () => this.request<Conversation[]>("/conversations");
  createConversation = (data_source_id: number, title?: string) => this.request<Conversation>("/conversations", { method: "POST", body: JSON.stringify({ data_source_id, title }) });
  messages = (conversationId: number) => this.request<ConversationMessage[]>(`/conversations/${conversationId}/messages`);
  sendMessage = (conversationId: number, content: string, document_ids: number[]) => this.request<{ task_id: number }>(`/conversations/${conversationId}/messages`, { method: "POST", body: JSON.stringify({ content, document_ids }) });
  task = (conversationId: number, taskId: number) => this.request<Task>(`/conversations/${conversationId}/tasks/${taskId}`);
  cancelTask = (conversationId: number, taskId: number) => this.request<Task>(`/conversations/${conversationId}/tasks/${taskId}/cancel`, { method: "POST" });
  retryTask = (conversationId: number, taskId: number) => this.request<{ task_id: number }>(`/conversations/${conversationId}/tasks/${taskId}/retry`, { method: "POST" });
  snapshots = (sourceId: number) => this.request<Snapshot[]>(`/company/data-sources/${sourceId}/schema-snapshots`);
  discover = (sourceId: number) => this.request<Snapshot>(`/company/data-sources/${sourceId}/discover-schema`, { method: "POST" });
  activateSnapshot = (sourceId: number, snapshotId: number) => this.request<Snapshot>(`/company/data-sources/${sourceId}/schema-snapshots/${snapshotId}/activate`, { method: "POST" });
  createDataSource = (payload: object) => this.request<DataSource>("/company/data-sources", { method: "POST", body: JSON.stringify(payload) });
  members = () => this.request<CompanyMember[]>("/company/members");
  updateMember = (memberId: number, payload: object) => this.request<CompanyMember>(`/company/members/${memberId}`, { method: "PATCH", body: JSON.stringify(payload) });
  createInvitation = (payload: { max_uses: number; expires_at?: string }) => this.request<CreatedCompanyInvitation>("/company/invitations", { method: "POST", body: JSON.stringify(payload) });
  invitations = () => this.request<CompanyInvitation[]>("/company/invitations");
  revokeInvitation = (invitationId: number) => this.request<CompanyInvitation>(`/company/invitations/${invitationId}/revoke`, { method: "POST" });
  membershipApplications = (status?: MembershipApplication["status"]) => this.request<MembershipApplication[]>(`/company/membership-applications${status ? `?status=${encodeURIComponent(status)}` : ""}`);
  approveMembershipApplication = (applicationId: number) => this.request<MembershipApplication>(`/company/membership-applications/${applicationId}/approve`, { method: "POST" });
  rejectMembershipApplication = (applicationId: number) => this.request<MembershipApplication>(`/company/membership-applications/${applicationId}/reject`, { method: "POST" });
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

export async function applyForMembership(payload: { name: string; username: string; password: string; invitation_code: string }): Promise<{ id: number; status: "pending"; created_at: string; reviewed_at: string | null }> {
  const response = await fetch(`${API_BASE}/auth/membership-applications`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const responsePayload = await response.json().catch(() => ({}));
    const message = responsePayload.message ?? responsePayload.detail ?? "申请提交失败，请稍后重试。";
    throw new ApiError(response.status, messageMap[message] ?? message);
  }
  return response.json() as Promise<{ id: number; status: "pending"; created_at: string; reviewed_at: string | null }>;
}

export async function bootstrapOwner(payload: { name: string; company_name: string; username: string; password: string }): Promise<{ access_token: string; expires_in: number }> {
  const response = await fetch(`${API_BASE}/auth/bootstrap-owner`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const responsePayload = await response.json().catch(() => ({}));
    const message = responsePayload.message ?? responsePayload.detail ?? "初始化公司失败，请稍后重试。";
    throw new ApiError(response.status, messageMap[message] ?? message);
  }
  return response.json() as Promise<{ access_token: string; expires_in: number }>;
}

export async function reapplyForMembership(payload: { username: string; password: string; invitation_code: string }): Promise<{ id: number; status: "pending"; created_at: string; reviewed_at: string | null }> {
  const response = await fetch(`${API_BASE}/auth/membership-applications/reapply`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const responsePayload = await response.json().catch(() => ({}));
    const message = responsePayload.message ?? responsePayload.detail ?? "重新申请失败，请稍后重试。";
    throw new ApiError(response.status, messageMap[message] ?? message);
  }
  return response.json() as Promise<{ id: number; status: "pending"; created_at: string; reviewed_at: string | null }>;
}
