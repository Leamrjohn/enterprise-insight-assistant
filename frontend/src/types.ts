export type Role = "owner" | "admin" | "analyst" | "viewer";
export type TaskStatus = "queued" | "running" | "retrying" | "completed" | "partial" | "failed" | "cancelled" | "needs_clarification";

export interface CurrentUser {
  id: number;
  name: string;
  username: string | null;
  role: Role;
  is_active: boolean;
  created_at: string;
  company_id: number;
  company_name: string;
  membership_status: string;
}

export interface DataSource {
  id: number;
  name: string;
  dialect: string;
  connection: { host: string; port: number; database: string; user: string; schema: string };
  credential_env_var: string;
  status: string;
  last_error: string | null;
  active_schema_snapshot_id: number | null;
}

export interface AssistantDataSource {
  id: number;
  name: string;
  status: string;
  active_schema_snapshot_id: number | null;
}

export interface DocumentItem {
  id: number;
  name: string;
  source: string;
  status: string;
  error_message: string | null;
  min_view_role: string;
  file_type: string | null;
  file_size: number | null;
  created_at: string | null;
}

export interface DocumentChunk {
  id: number;
  document_id: number;
  chunk_index: number;
  content: string;
  token_count: number;
  page_number: number | null;
  created_at: string;
}

export interface Snapshot {
  id: number;
  data_source_id: number;
  fingerprint: string;
  catalog: Record<string, unknown>;
  discovered_by_user_id: number;
  created_at: string;
}

export interface CompanyMember {
  id: number;
  user_id: number;
  user_name: string;
  username: string | null;
  is_active: boolean;
  role: Role;
  status: "approved" | "disabled" | "rejected";
  created_at: string;
}

export interface CreatedCompanyInvitation {
  id: number;
  code: string;
  max_uses: number;
  expires_at: string | null;
}

export interface CompanyInvitation {
  id: number;
  max_uses: number;
  used_count: number;
  is_active: boolean;
  expires_at: string | null;
  created_at: string;
}

export interface MembershipApplication {
  id: number;
  user_id: number;
  user_name: string | null;
  username: string | null;
  status: "pending" | "approved" | "rejected";
  created_at: string;
  reviewed_at: string | null;
}

export interface Conversation { id: number; title: string | null; data_source_id: number; created_at: string; updated_at: string; }
export interface ConversationMessage { id: number; role: "user" | "assistant"; content: string | null; status: TaskStatus; analysis_task_id: number | null; created_at: string; }

export interface ReportItem { statement?: string; action?: string; rationale?: string; support_level?: string; priority?: string; verification_metric?: string; }
export interface DataEvidence {
  evidence_id: string;
  purpose: string;
  columns: string[];
  rows: unknown[][];
}
export interface DocumentCitation {
  chunk_id: number;
  document_id: number | null;
  excerpt: string;
  score: number | null;
}
export interface Report {
  executive_summary?: string;
  confirmed_facts?: ReportItem[];
  hypotheses?: ReportItem[];
  recommendations?: ReportItem[];
  data_evidence?: DataEvidence[];
  document_citations?: DocumentCitation[];
  limitations?: Array<{ message?: string; statement?: string } | string>;
}
export interface Task { id: number; status: TaskStatus; stage: string; error_message: string | null; result_summary: string | null; report: Report | null; result_data: Record<string, unknown> | null; }
