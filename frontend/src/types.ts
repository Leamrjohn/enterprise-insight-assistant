export type Role = "owner" | "admin" | "analyst" | "viewer";
export type TaskStatus = "queued" | "running" | "retrying" | "awaiting_review" | "completed" | "partial" | "failed" | "cancelled" | "needs_clarification";

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
  company_id: number | null;
  uploaded_by_user_id: number;
  name: string;
  content: string | null;
  source: string;
  status: string;
  error_message: string | null;
  min_view_role: string;
  file_type: string | null;
  file_size: number | null;
  created_at: string | null;
  updated_at: string | null;
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

export interface Conversation { id: number; title: string | null; data_source_id: number | null; created_at: string; updated_at: string; }
export interface ConversationMessage { id: number; role: "user" | "assistant"; content: string | null; status: TaskStatus; analysis_task_id: number | null; created_at: string; updated_at: string; }

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
export interface TaskObservability {
  request_id: string | null;
  active_execution_id: string | null;
  latest_checkpoint: { completed_node: string | null; next_node: string | null; error_code: string | null; recovery_instruction: string | null; created_at: string } | null;
  model_usage: { calls: number; tokens: number; cost: string; budget: Record<string, unknown> | null; usage: Record<string, unknown> | null };
}
export interface Task { id: number; conversation_id: number | null; status: TaskStatus; stage: string; attempt_count: number; duration_ms: number | null; error_type: string | null; error_message: string | null; result_summary: string | null; assistant_message_id: number | null; assistant_content: string | null; report: Report | null; report_draft: Report | null; review: { id: number; status: "pending" | "approved" | "rejected"; reason_code: string; decision_note: string | null; reviewed_at: string | null } | null; observability: TaskObservability | null; created_at: string | null; updated_at: string | null; }
export interface ReviewRequest {
  id: number;
  task_id: number;
  task_question: string;
  status: "pending" | "approved" | "rejected";
  reason_code: string;
  report_draft: Report | null;
  draft_error: "missing" | "invalid" | null;
  created_at: string;
}
export interface TaskMetrics { total_tasks: number; terminal_tasks: number; completed_tasks: number; partial_tasks: number; failed_tasks: number; cancelled_tasks: number; completion_rate: number; partial_rate: number; retry_count: number; duration_p50_ms: number | null; duration_p95_ms: number | null; model_calls: number; model_tokens: number; model_cost: string; rag_sufficient_rate: number | null; citation_failure_rate: number | null; }
