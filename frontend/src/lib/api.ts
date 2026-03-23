import type {
  ApiErrorPayload,
  AuditLogRecord,
  AuthResponse,
  CaseComment,
  CaseRecord,
  CaseSummaryReport,
  DocumentRecord,
  SessionPayload,
} from "@/lib/types";

export class ApiError extends Error {
  code?: string;
  requestId?: string;

  constructor(message: string, options?: { code?: string; requestId?: string }) {
    super(message);
    this.name = "ApiError";
    this.code = options?.code;
    this.requestId = options?.requestId;
  }
}

const API_ROOT = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000").replace(
  /\/$/,
  "",
);
const API_V1 = `${API_ROOT}/api/v1`;

type RequestOptions = {
  method?: string;
  token?: string | null;
  body?: unknown;
};

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const response = await fetch(`${API_V1}${path}`, {
    method: options.method ?? "GET",
    headers: {
      "Content-Type": "application/json",
      ...(options.token ? { Authorization: `Bearer ${options.token}` } : {}),
    },
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    cache: "no-store",
  });

  if (!response.ok) {
    let payload: ApiErrorPayload | null = null;
    try {
      payload = (await response.json()) as ApiErrorPayload;
    } catch {
      payload = null;
    }
    throw new ApiError(
      payload?.error?.message ?? `Request failed with status ${response.status}.`,
      {
        code: payload?.error?.code,
        requestId: payload?.error?.request_id,
      },
    );
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export async function register(payload: {
  organization_name: string;
  organization_slug: string;
  first_name: string;
  last_name: string;
  email: string;
  password: string;
}) {
  return request<AuthResponse>("/auth/register", {
    method: "POST",
    body: payload,
  });
}

export async function login(payload: {
  email: string;
  password: string;
  organization_slug?: string;
}) {
  return request<AuthResponse>("/auth/login", {
    method: "POST",
    body: payload,
  });
}

export async function getMe(token: string) {
  return request<SessionPayload>("/me", {
    token,
  });
}

export async function getCaseSummary(token: string) {
  return request<CaseSummaryReport>("/reports/cases/summary", {
    token,
  });
}

export async function listCases(token: string, query?: { q?: string }) {
  if (query?.q) {
    const encodedQuery = encodeURIComponent(query.q);
    return request<CaseRecord[]>(`/search/cases?q=${encodedQuery}&limit=12`, {
      token,
    });
  }
  return request<CaseRecord[]>("/cases?limit=12&offset=0", {
    token,
  });
}

export async function getCase(token: string, caseId: string) {
  return request<CaseRecord>(`/cases/${caseId}`, {
    token,
  });
}

export async function listCaseComments(token: string, caseId: string) {
  return request<CaseComment[]>(`/cases/${caseId}/comments`, {
    token,
  });
}

export async function createCaseComment(token: string, caseId: string, body: string) {
  return request<CaseComment>(`/cases/${caseId}/comments`, {
    method: "POST",
    token,
    body: { body },
  });
}

export async function listCaseDocuments(token: string, caseId: string) {
  return request<DocumentRecord[]>(`/cases/${caseId}/documents`, {
    token,
  });
}

export async function uploadCaseDocument(
  token: string,
  caseId: string,
  payload: {
    title: string;
    document_type: string;
    original_filename: string;
    mime_type: string;
    content_base64: string;
  },
) {
  return request<DocumentRecord>(`/cases/${caseId}/documents`, {
    method: "POST",
    token,
    body: payload,
  });
}

export async function listCaseAuditLog(token: string, caseId: string) {
  return request<AuditLogRecord[]>(`/cases/${caseId}/audit-log`, {
    token,
  });
}
