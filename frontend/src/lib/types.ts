export type User = {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  is_active: boolean;
  created_at: string;
};

export type Organization = {
  id: string;
  name: string;
  slug: string;
  status: string;
  created_at: string;
};

export type Membership = {
  id: string;
  role: string;
  is_active: boolean;
  joined_at: string;
};

export type SessionPayload = {
  user: User;
  organization: Organization;
  membership: Membership;
};

export type AuthResponse = SessionPayload & {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  refresh_token_expires_in: number;
};

export type CaseSummaryReport = {
  total_cases: number;
  active_cases: number;
  archived_cases: number;
  overdue_cases: number;
  due_next_7_days: number;
  status_counts: Record<string, number>;
  priority_counts: Record<string, number>;
};

export type CaseRecord = {
  id: string;
  external_id: string | null;
  title: string;
  description: string | null;
  status: string;
  priority: string;
  owner_user_id: string | null;
  created_by: string;
  due_date: string | null;
  archived_at: string | null;
  created_at: string;
  updated_at: string;
};

export type CaseComment = {
  id: string;
  case_id: string;
  author_user_id: string;
  body: string;
  created_at: string;
  updated_at: string;
};

export type DocumentRecord = {
  id: string;
  case_id: string;
  current_version_id: string | null;
  document_type: string;
  title: string;
  status: string;
  uploaded_by: string;
  checksum: string | null;
  mime_type: string | null;
  size_bytes: number | null;
  storage_key: string | null;
  deleted_at: string | null;
  created_at: string;
  updated_at: string;
};

export type AuditLogRecord = {
  id: string;
  actor_user_id: string | null;
  event_type: string;
  entity_type: string;
  entity_id: string;
  old_values_json: Record<string, unknown> | null;
  new_values_json: Record<string, unknown> | null;
  metadata_json: Record<string, unknown> | null;
  created_at: string;
};

export type AssistantConversation = {
  id: string;
  case_id: string;
  title: string;
  prompt_mode: string;
  created_by_user_id: string;
  last_message_at: string | null;
  created_at: string;
  updated_at: string;
};

export type AssistantCitation = {
  document_id: string;
  document_title: string;
  document_type: string;
  document_status: string;
  document_version_id: string | null;
  original_filename: string | null;
  excerpt: string;
  score: number;
};

export type AssistantMessage = {
  id: string;
  conversation_id: string;
  actor_user_id: string | null;
  role: "user" | "assistant";
  prompt_mode: string;
  content: string;
  citations_json: AssistantCitation[];
  metadata_json: Record<string, unknown>;
  created_at: string;
};

export type AssistantExchange = {
  conversation: AssistantConversation;
  user_message: AssistantMessage;
  assistant_message: AssistantMessage;
};

export type ApiErrorPayload = {
  error?: {
    code?: string;
    message?: string;
    request_id?: string;
  };
};

export type AuthStorageState = {
  accessToken: string;
  refreshToken: string;
  session: SessionPayload;
};
