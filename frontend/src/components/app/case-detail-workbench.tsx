"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { CaseAssistantPanel } from "@/components/app/case-assistant-panel";
import { Badge, priorityTone, statusTone } from "@/components/ui/badge";
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
      auditLog.slice(-12).reverse().map((entry) => ({
        ...entry,
        summary:
          typeof entry.metadata_json?.body_excerpt === "string"
            ? entry.metadata_json.body_excerpt
            : entry.new_values_json?.status && typeof entry.new_values_json.status === "string"
              ? `Status changed to ${formatEnumLabel(entry.new_values_json.status)}`
              : null,
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
      <div className="space-y-4">
        <BackLink />
        <p className="notice-error">{errorMessage}</p>
      </div>
    );
  }

  if (loadState === "loading" || !caseRecord) {
    return <p className="empty">Loading case…</p>;
  }

  return (
    <div className="space-y-5">
      <div>
        <BackLink />
        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-2">
          <h1 className="text-xl font-semibold">{caseRecord.title}</h1>
          <Badge value={caseRecord.status} tone={statusTone[caseRecord.status] ?? "neutral"} />
          <Badge
            value={caseRecord.priority}
            tone={priorityTone[caseRecord.priority] ?? "neutral"}
          />
        </div>
        {caseRecord.description ? (
          <p className="mt-1.5 max-w-3xl text-muted">{caseRecord.description}</p>
        ) : null}
        <dl className="mt-3 flex flex-wrap gap-x-8 gap-y-2">
          <Meta label="Reference" value={caseRecord.external_id ?? "–"} mono />
          <Meta label="Due" value={caseRecord.due_date ? formatDate(caseRecord.due_date) : "–"} />
          <Meta label="Created" value={formatDateTime(caseRecord.created_at)} />
          <Meta label="Updated" value={formatDateTime(caseRecord.updated_at)} />
        </dl>
      </div>

      {errorMessage ? <p className="notice-error">{errorMessage}</p> : null}

      <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(0,0.9fr)]">
        <div className="min-w-0 space-y-5">
          <section className="panel">
            <div className="panel-head">
              <h2 className="panel-title">Documents</h2>
              <span className="count">{documents.length}</span>
            </div>
            {documents.length === 0 ? (
              <p className="empty">No documents attached.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="data-table min-w-[560px]">
                  <thead>
                    <tr>
                      <th>Title</th>
                      <th>Type</th>
                      <th>Status</th>
                      <th>Uploaded</th>
                    </tr>
                  </thead>
                  <tbody>
                    {documents.map((document) => (
                      <tr key={document.id}>
                        <td>
                          <span className="font-medium">{document.title}</span>
                          {document.mime_type ? (
                            <span className="block font-mono text-xs text-muted">
                              {document.mime_type}
                            </span>
                          ) : null}
                        </td>
                        <td className="whitespace-nowrap">
                          {formatEnumLabel(document.document_type)}
                        </td>
                        <td>
                          <Badge
                            value={document.status}
                            tone={statusTone[document.status] ?? "neutral"}
                          />
                        </td>
                        <td className="whitespace-nowrap text-muted">
                          {formatDateTime(document.created_at)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            <form
              className="grid gap-3 border-t border-line bg-paper/50 p-4 sm:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)]"
              onSubmit={handleUploadSubmit}
            >
              <div className="field-shell">
                <label className="field-label" htmlFor="document-title">
                  Title
                </label>
                <input
                  id="document-title"
                  value={uploadTitle}
                  onChange={(event) => setUploadTitle(event.target.value)}
                  placeholder="Defaults to the file name"
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

              <div className="flex items-end">
                <Button disabled={uploadSubmitting} fullWidth type="submit">
                  {uploadSubmitting ? "Uploading…" : "Upload document"}
                </Button>
              </div>
            </form>
          </section>

          <section className="panel">
            <div className="panel-head">
              <h2 className="panel-title">Comments</h2>
              <span className="count">{comments.length}</span>
            </div>
            {comments.length === 0 ? (
              <p className="empty">No comments yet.</p>
            ) : (
              <ul>
                {comments.map((comment) => (
                  <li key={comment.id} className="border-b border-line px-4 py-3">
                    <p className="whitespace-pre-line">{comment.body}</p>
                    <p className="mt-1 text-xs text-muted">{formatDateTime(comment.created_at)}</p>
                  </li>
                ))}
              </ul>
            )}
            <form className="space-y-2 p-4" onSubmit={handleCommentSubmit}>
              <label className="field-label" htmlFor="comment-body">
                Add comment
              </label>
              <textarea
                id="comment-body"
                value={commentBody}
                onChange={(event) => setCommentBody(event.target.value)}
                required
              />
              <Button disabled={commentSubmitting} type="submit" variant="secondary">
                {commentSubmitting ? "Posting…" : "Post comment"}
              </Button>
            </form>
          </section>

          <section className="panel">
            <div className="panel-head">
              <h2 className="panel-title">Activity</h2>
              <span className="count">Last {timeline.length}</span>
            </div>
            {timeline.length === 0 ? (
              <p className="empty">No activity recorded.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="data-table min-w-[480px]">
                  <tbody>
                    {timeline.map((entry) => (
                      <tr key={entry.id}>
                        <td className="whitespace-nowrap text-muted">
                          {formatDateTime(entry.created_at)}
                        </td>
                        <td className="whitespace-nowrap font-mono text-xs">{entry.event_type}</td>
                        <td className="text-muted">{entry.summary ?? ""}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </div>

        <CaseAssistantPanel caseId={caseId} />
      </div>
    </div>
  );
}

function BackLink() {
  return (
    <Link className="text-sm text-accent hover:underline" href="/workspace">
      ← All cases
    </Link>
  );
}

function Meta({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <dt className="text-xs text-muted">{label}</dt>
      <dd className={mono ? "font-mono text-[13px]" : undefined}>{value}</dd>
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
