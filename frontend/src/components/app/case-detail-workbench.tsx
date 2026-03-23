"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { CaseAssistantPanel } from "@/components/app/case-assistant-panel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/auth-context";
import {
  ApiError,
  createCaseComment,
  getCase,
  listCaseAuditLog,
  listCaseComments,
  listCaseDocuments,
  uploadCaseDocument,
} from "@/lib/api";
import { formatDate, formatDateTime, formatEnumLabel } from "@/lib/format";
import type { AuditLogRecord, CaseComment, CaseRecord, DocumentRecord } from "@/lib/types";

const documentTypeOptions = [
  "invoice",
  "contract",
  "id_document",
  "statement",
  "attachment",
  "other",
];

const statusTone: Record<string, "neutral" | "success" | "warning" | "danger"> = {
  approved: "success",
  ready: "success",
  in_review: "warning",
  waiting_for_documents: "warning",
  rejected: "danger",
  failed: "danger",
  archived: "neutral",
  queued: "neutral",
  processing: "warning",
};

type LoadState = "loading" | "ready" | "error";

type CaseDetailWorkbenchProps = {
  caseId: string;
};

export function CaseDetailWorkbench({ caseId }: CaseDetailWorkbenchProps) {
  const { accessToken } = useAuth();
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [caseRecord, setCaseRecord] = useState<CaseRecord | null>(null);
  const [comments, setComments] = useState<CaseComment[]>([]);
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [auditLog, setAuditLog] = useState<AuditLogRecord[]>([]);
  const [commentBody, setCommentBody] = useState("");
  const [uploadTitle, setUploadTitle] = useState("");
  const [documentType, setDocumentType] = useState("other");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [commentSubmitting, setCommentSubmitting] = useState(false);
  const [uploadSubmitting, setUploadSubmitting] = useState(false);

  const loadCaseData = useCallback(
    async (token: string) => {
      setLoadState("loading");
      try {
        const [nextCase, nextComments, nextDocuments, nextAudit] = await Promise.all([
          getCase(token, caseId),
          listCaseComments(token, caseId),
          listCaseDocuments(token, caseId),
          listCaseAuditLog(token, caseId),
        ]);
        setCaseRecord(nextCase);
        setComments(nextComments);
        setDocuments(nextDocuments);
        setAuditLog(nextAudit);
        setErrorMessage(null);
        setLoadState("ready");
      } catch (error) {
        setLoadState("error");
        setErrorMessage(error instanceof ApiError ? error.message : "Failed to load case.");
      }
    },
    [caseId],
  );

  useEffect(() => {
    if (accessToken == null) {
      return;
    }
    void loadCaseData(accessToken);
  }, [accessToken, loadCaseData]);

  const timeline = useMemo(
    () =>
      auditLog.slice(-8).reverse().map((entry) => ({
        ...entry,
        summary:
          typeof entry.metadata_json?.body_excerpt === "string"
            ? entry.metadata_json.body_excerpt
            : entry.new_values_json?.status && typeof entry.new_values_json.status === "string"
              ? `Status changed to ${formatEnumLabel(entry.new_values_json.status)}`
              : "Captured in audit log",
      })),
    [auditLog],
  );

  async function handleCommentSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!accessToken || !commentBody.trim()) {
      return;
    }
    try {
      setCommentSubmitting(true);
      await createCaseComment(accessToken, caseId, commentBody.trim());
      setCommentBody("");
      await loadCaseData(accessToken);
    } catch (error) {
      setErrorMessage(error instanceof ApiError ? error.message : "Comment creation failed.");
    } finally {
      setCommentSubmitting(false);
    }
  }

  async function handleUploadSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!accessToken || !selectedFile) {
      return;
    }
    try {
      setUploadSubmitting(true);
      const contentBase64 = await readFileAsBase64(selectedFile);
      await uploadCaseDocument(accessToken, caseId, {
        title: uploadTitle.trim() || selectedFile.name.replace(/\.[^.]+$/, ""),
        document_type: documentType,
        original_filename: selectedFile.name,
        mime_type: selectedFile.type || "application/octet-stream",
        content_base64: contentBase64,
      });
      setUploadTitle("");
      setSelectedFile(null);
      await loadCaseData(accessToken);
    } catch (error) {
      setErrorMessage(error instanceof ApiError ? error.message : "Document upload failed.");
    } finally {
      setUploadSubmitting(false);
    }
  }

  if (loadState === "error") {
    return (
      <section className="surface-card border-rose-200 bg-rose-50/75">
        <p className="text-xs font-semibold uppercase tracking-[0.26em] text-rose-700">
          Case detail error
        </p>
        <p className="mt-3 text-base text-rose-900">{errorMessage}</p>
      </section>
    );
  }

  if (loadState === "loading" || !caseRecord) {
    return (
      <section className="surface-card">
        <p className="text-xs font-semibold uppercase tracking-[0.26em] text-slate-500">
          Case detail
        </p>
        <p className="mt-4 text-base text-slate-600">Loading case, documents and operator notes…</p>
      </section>
    );
  }

  return (
    <div className="space-y-6">
      <section className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <div className="surface-card">
          <div className="flex flex-wrap items-center gap-3">
            <p className="text-xs font-semibold uppercase tracking-[0.28em] text-slate-500">
              Case detail
            </p>
            <Badge value={caseRecord.status} tone={statusTone[caseRecord.status] ?? "neutral"} />
            <Badge value={caseRecord.priority} />
          </div>

          <h1 className="mt-4 text-4xl font-semibold tracking-[-0.05em] text-slate-950">
            {caseRecord.title}
          </h1>
          <p className="mt-4 max-w-3xl text-base leading-7 text-slate-600">
            {caseRecord.description || "No description has been added to this case yet."}
          </p>

          <div className="mt-6 grid gap-4 sm:grid-cols-3">
            <InfoTile
              label="External reference"
              value={caseRecord.external_id || "No external id"}
              helper="Useful for cross-system lookup"
            />
            <InfoTile
              label="Due date"
              value={formatDate(caseRecord.due_date)}
              helper="Visible operator deadline"
            />
            <InfoTile
              label="Last updated"
              value={formatDateTime(caseRecord.updated_at)}
              helper="Latest backend activity"
            />
          </div>
        </div>

        <div className="surface-card">
          <CaseAssistantPanel caseId={caseId} />
        </div>
      </section>

      {errorMessage ? (
        <section className="surface-card border-amber-200 bg-amber-50/80">
          <p className="text-xs font-semibold uppercase tracking-[0.26em] text-amber-700">
            Workspace notice
          </p>
          <p className="mt-3 text-base text-amber-900">{errorMessage}</p>
        </section>
      ) : null}

      <section className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <div className="space-y-6">
          <div className="surface-card">
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.28em] text-slate-500">
                  Documents
                </p>
                <h2 className="mt-2 text-2xl font-semibold tracking-[-0.04em] text-slate-950">
                  Uploaded evidence
                </h2>
              </div>
              <span className="rounded-full bg-slate-200/80 px-3 py-1 text-xs font-semibold uppercase tracking-[0.2em] text-slate-700">
                {documents.length} total
              </span>
            </div>

            <div className="mt-5 grid gap-4">
              {documents.length === 0 ? (
                <div className="rounded-[1.6rem] border border-dashed border-slate-300 bg-white/55 px-5 py-8 text-sm text-slate-500">
                  No documents yet. Use the upload form to attach the first document to this case.
                </div>
              ) : (
                documents.map((document) => (
                  <article
                    key={document.id}
                    className="rounded-[1.6rem] border border-slate-200/80 bg-white/70 p-5"
                  >
                    <div className="flex flex-wrap items-center gap-3">
                      <p className="text-lg font-semibold text-slate-900">{document.title}</p>
                      <Badge
                        value={document.status}
                        tone={statusTone[document.status] ?? "neutral"}
                      />
                    </div>
                    <div className="mt-4 grid gap-3 sm:grid-cols-3">
                      <MiniField
                        label="Type"
                        value={formatEnumLabel(document.document_type)}
                      />
                      <MiniField
                        label="MIME type"
                        value={document.mime_type ?? "Unknown"}
                      />
                      <MiniField
                        label="Uploaded"
                        value={formatDateTime(document.created_at)}
                      />
                    </div>
                  </article>
                ))
              )}
            </div>
          </div>

          <div className="surface-card">
            <p className="text-xs font-semibold uppercase tracking-[0.28em] text-slate-500">
              Upload document
            </p>
            <form className="mt-5 grid gap-4 md:grid-cols-2" onSubmit={handleUploadSubmit}>
              <div className="field-shell md:col-span-2">
                <label className="field-label" htmlFor="document-title">
                  Title
                </label>
                <input
                  id="document-title"
                  value={uploadTitle}
                  onChange={(event) => setUploadTitle(event.target.value)}
                  placeholder="Repair estimate"
                />
              </div>

              <div className="field-shell">
                <label className="field-label" htmlFor="document-type">
                  Document type
                </label>
                <select
                  id="document-type"
                  value={documentType}
                  onChange={(event) => setDocumentType(event.target.value)}
                >
                  {documentTypeOptions.map((option) => (
                    <option key={option} value={option}>
                      {formatEnumLabel(option)}
                    </option>
                  ))}
                </select>
              </div>

              <div className="field-shell">
                <label className="field-label" htmlFor="document-file">
                  File
                </label>
                <input
                  id="document-file"
                  type="file"
                  onChange={(event) => {
                    const nextFile = event.target.files?.[0] ?? null;
                    setSelectedFile(nextFile);
                    if (nextFile && !uploadTitle.trim()) {
                      setUploadTitle(nextFile.name.replace(/\.[^.]+$/, ""));
                    }
                  }}
                  required
                />
              </div>

              <div className="md:col-span-2">
                <Button disabled={uploadSubmitting} fullWidth type="submit">
                  {uploadSubmitting ? "Uploading…" : "Upload document"}
                </Button>
              </div>
            </form>
          </div>
        </div>

        <div className="space-y-6">
          <div className="surface-card">
            <p className="text-xs font-semibold uppercase tracking-[0.28em] text-slate-500">
              Comments
            </p>
            <form className="mt-5 space-y-4" onSubmit={handleCommentSubmit}>
              <div className="field-shell">
                <label className="field-label" htmlFor="comment-body">
                  Add operator note
                </label>
                <textarea
                  id="comment-body"
                  value={commentBody}
                  onChange={(event) => setCommentBody(event.target.value)}
                  placeholder="Record what changed, what is blocked or what the next reviewer should verify."
                  required
                />
              </div>
              <Button disabled={commentSubmitting} fullWidth type="submit">
                {commentSubmitting ? "Posting…" : "Post comment"}
              </Button>
            </form>

            <div className="mt-5 space-y-3">
              {comments.length === 0 ? (
                <div className="rounded-[1.5rem] border border-dashed border-slate-300 bg-white/55 px-4 py-6 text-sm text-slate-500">
                  No comments on this case yet.
                </div>
              ) : (
                comments.map((comment) => (
                  <article
                    key={comment.id}
                    className="rounded-[1.5rem] border border-slate-200/80 bg-white/70 px-4 py-4"
                  >
                    <p className="text-sm leading-7 text-slate-800">{comment.body}</p>
                    <p className="mt-2 text-xs font-medium uppercase tracking-[0.18em] text-slate-500">
                      {formatDateTime(comment.created_at)}
                    </p>
                  </article>
                ))
              )}
            </div>
          </div>

          <div className="surface-card">
            <p className="text-xs font-semibold uppercase tracking-[0.28em] text-slate-500">
              Audit trail
            </p>
            <div className="mt-5 space-y-3">
              {timeline.length === 0 ? (
                <div className="rounded-[1.5rem] border border-dashed border-slate-300 bg-white/55 px-4 py-6 text-sm text-slate-500">
                  Audit entries will appear as case activity grows.
                </div>
              ) : (
                timeline.map((entry) => (
                  <article
                    key={entry.id}
                    className="rounded-[1.5rem] border border-slate-200/80 bg-white/70 px-4 py-4"
                  >
                    <div className="flex items-center justify-between gap-4">
                      <p className="text-sm font-semibold uppercase tracking-[0.14em] text-slate-700">
                        {entry.event_type.replaceAll(".", " ")}
                      </p>
                      <p className="text-xs uppercase tracking-[0.18em] text-slate-500">
                        {formatDateTime(entry.created_at)}
                      </p>
                    </div>
                    <p className="mt-2 text-sm leading-7 text-slate-600">{entry.summary}</p>
                  </article>
                ))
              )}
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}

function InfoTile({
  label,
  value,
  helper,
}: {
  label: string;
  value: string;
  helper: string;
}) {
  return (
    <div className="rounded-[1.5rem] border border-slate-200/80 bg-white/70 p-4">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">{label}</p>
      <p className="mt-3 text-lg font-semibold tracking-[-0.03em] text-slate-900">{value}</p>
      <p className="mt-2 text-sm text-slate-600">{helper}</p>
    </div>
  );
}

function MiniField({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl bg-slate-100/75 px-4 py-3">
      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">
        {label}
      </p>
      <p className="mt-2 text-sm font-medium text-slate-800">{value}</p>
    </div>
  );
}

function readFileAsBase64(file: File) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("Failed to read file."));
    reader.onload = () => {
      const result = reader.result;
      if (typeof result !== "string") {
        reject(new Error("Unexpected file reader output."));
        return;
      }
      const [, base64Payload] = result.split(",", 2);
      resolve(base64Payload ?? "");
    };
    reader.readAsDataURL(file);
  });
}
