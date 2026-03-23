"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/auth-context";
import { ApiError, createCase, getCaseSummary, listCases } from "@/lib/api";
import { formatDate, formatDateTime, formatEnumLabel } from "@/lib/format";
import type { CaseRecord, CaseSummaryReport } from "@/lib/types";

const statusTone: Record<string, "neutral" | "success" | "warning" | "danger"> = {
  approved: "success",
  ready: "success",
  in_review: "warning",
  waiting_for_documents: "warning",
  rejected: "danger",
  failed: "danger",
  archived: "neutral",
};

type LoadState = "loading" | "ready" | "error";

export function WorkspaceDashboard() {
  const router = useRouter();
  const { accessToken } = useAuth();
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [summary, setSummary] = useState<CaseSummaryReport | null>(null);
  const [cases, setCases] = useState<CaseRecord[]>([]);
  const [query, setQuery] = useState("");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [newCaseTitle, setNewCaseTitle] = useState("");
  const [newCaseExternalId, setNewCaseExternalId] = useState("");
  const [newCaseDescription, setNewCaseDescription] = useState("");
  const [newCasePriority, setNewCasePriority] = useState("normal");
  const [isCreatingCase, setIsCreatingCase] = useState(false);

  const loadDashboard = useCallback(async (token: string) => {
    try {
      setLoadState("loading");
      const [nextSummary, nextCases] = await Promise.all([
        getCaseSummary(token),
        listCases(token),
      ]);
      setSummary(nextSummary);
      setCases(nextCases);
      setErrorMessage(null);
      setLoadState("ready");
    } catch (error) {
      setLoadState("error");
      setErrorMessage(
        error instanceof ApiError ? error.message : "Failed to load dashboard data.",
      );
    }
  }, []);

  useEffect(() => {
    if (accessToken == null) {
      return;
    }
    const token = accessToken;

    let isCancelled = false;
    async function loadDashboardSafe() {
      await loadDashboard(token);
      if (isCancelled) {
        return;
      }
    }

    void loadDashboardSafe();
    return () => {
      isCancelled = true;
    };
  }, [accessToken, loadDashboard]);

  async function handleSearch() {
    if (!accessToken) {
      return;
    }
    try {
      setLoadState("loading");
      const nextCases = await listCases(accessToken, {
        q: query.trim() || undefined,
      });
      setCases(nextCases);
      setLoadState("ready");
    } catch (error) {
      setLoadState("error");
      setErrorMessage(error instanceof ApiError ? error.message : "Case search failed.");
    }
  }

  async function handleCreateCase(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!accessToken || !newCaseTitle.trim()) {
      return;
    }

    try {
      setIsCreatingCase(true);
      const createdCase = await createCase(accessToken, {
        title: newCaseTitle.trim(),
        description: newCaseDescription.trim() || undefined,
        external_id: newCaseExternalId.trim() || undefined,
        priority: newCasePriority,
      });
      setNewCaseTitle("");
      setNewCaseExternalId("");
      setNewCaseDescription("");
      setNewCasePriority("normal");
      setErrorMessage(null);
      router.push(`/workspace/cases/${createdCase.id}`);
    } catch (error) {
      setErrorMessage(error instanceof ApiError ? error.message : "Case creation failed.");
    } finally {
      setIsCreatingCase(false);
    }
  }

  const prioritySnapshot = useMemo(() => {
    if (!summary) {
      return [];
    }
    return Object.entries(summary.priority_counts).sort((left, right) => right[1] - left[1]);
  }, [summary]);

  return (
    <div className="space-y-6">
      <section className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <div className="surface-card">
          <p className="text-xs font-semibold uppercase tracking-[0.3em] text-slate-500">
            Workspace health
          </p>
          <div className="mt-5 flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <h2 className="text-4xl font-semibold tracking-[-0.05em] text-slate-950 md:text-5xl">
                Review-heavy operations, now visible.
              </h2>
              <p className="mt-4 max-w-2xl text-base leading-7 text-slate-600">
                Use the existing reporting surfaces to surface workload, due dates and active
                cases. The next steps will wire this dashboard into assistant flows and document
                retrieval.
              </p>
            </div>
            <div className="rounded-[1.7rem] bg-slate-950 px-5 py-4 text-slate-50">
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">
                Current baseline
              </p>
              <p className="mt-3 text-3xl font-semibold tracking-[-0.04em]">
                {summary?.active_cases ?? "—"}
              </p>
              <p className="mt-1 text-sm text-slate-300">active cases in the workspace</p>
            </div>
          </div>
        </div>

        <div className="surface-card">
          <p className="text-xs font-semibold uppercase tracking-[0.3em] text-slate-500">
            Search desk
          </p>
          <div className="mt-4 flex flex-col gap-3 sm:flex-row">
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search by title, external id or description"
            />
            <Button onClick={() => void handleSearch()}>Search cases</Button>
          </div>
          <p className="mt-4 text-sm leading-7 text-slate-600">
            Use the current backend search API as the main entry point for operators jumping
            between cases.
          </p>

          <form className="mt-6 grid gap-4" onSubmit={handleCreateCase}>
            <div className="field-shell">
              <label className="field-label" htmlFor="new-case-title">
                Create case
              </label>
              <input
                id="new-case-title"
                value={newCaseTitle}
                onChange={(event) => setNewCaseTitle(event.target.value)}
                placeholder="New motor claim"
                required
              />
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="field-shell">
                <label className="field-label" htmlFor="new-case-external-id">
                  External id
                </label>
                <input
                  id="new-case-external-id"
                  value={newCaseExternalId}
                  onChange={(event) => setNewCaseExternalId(event.target.value)}
                  placeholder="CLM-2026-1049"
                />
              </div>

              <div className="field-shell">
                <label className="field-label" htmlFor="new-case-priority">
                  Priority
                </label>
                <select
                  id="new-case-priority"
                  value={newCasePriority}
                  onChange={(event) => setNewCasePriority(event.target.value)}
                >
                  <option value="low">Low</option>
                  <option value="normal">Normal</option>
                  <option value="high">High</option>
                  <option value="urgent">Urgent</option>
                </select>
              </div>
            </div>

            <div className="field-shell">
              <label className="field-label" htmlFor="new-case-description">
                Description
              </label>
              <textarea
                id="new-case-description"
                value={newCaseDescription}
                onChange={(event) => setNewCaseDescription(event.target.value)}
                placeholder="What should the team know before opening the case?"
              />
            </div>

            <Button disabled={isCreatingCase} type="submit">
              {isCreatingCase ? "Creating…" : "Create and open case"}
            </Button>
          </form>
        </div>
      </section>

      {loadState === "error" ? (
        <section className="surface-card border-rose-200 bg-rose-50/75">
          <p className="text-xs font-semibold uppercase tracking-[0.26em] text-rose-700">
            Dashboard error
          </p>
          <p className="mt-3 text-base text-rose-900">{errorMessage}</p>
        </section>
      ) : null}

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="Total cases" value={summary?.total_cases} helper="All tracked cases" />
        <MetricCard
          label="Due in 7 days"
          value={summary?.due_next_7_days}
          helper="Short-term workload pressure"
        />
        <MetricCard
          label="Overdue"
          value={summary?.overdue_cases}
          helper="Needs immediate triage"
        />
        <MetricCard
          label="Archived"
          value={summary?.archived_cases}
          helper="Completed or retired work"
        />
      </section>

      <section className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
        <div id="cases" className="surface-card">
          <div className="flex items-center justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.28em] text-slate-500">
                Recent cases
              </p>
              <h2 className="mt-2 text-2xl font-semibold tracking-[-0.04em] text-slate-950">
                Cases worth opening next
              </h2>
            </div>
            <span className="rounded-full bg-slate-200/80 px-3 py-1 text-xs font-semibold uppercase tracking-[0.2em] text-slate-700">
              {cases.length} loaded
            </span>
          </div>

          <div className="mt-5 overflow-hidden rounded-[1.7rem] border border-slate-200/80">
            <div className="grid grid-cols-[1.4fr_0.7fr_0.7fr_0.7fr] gap-4 bg-slate-950 px-5 py-3 text-xs font-semibold uppercase tracking-[0.2em] text-slate-300">
              <span>Case</span>
              <span>Status</span>
              <span>Priority</span>
              <span>Updated</span>
            </div>
            <div className="divide-y divide-slate-200/80 bg-white/70">
              {loadState === "loading" ? (
                <div className="px-5 py-6 text-sm text-slate-500">Loading cases…</div>
              ) : cases.length === 0 ? (
                <div className="px-5 py-6 text-sm text-slate-500">
                  No cases found for this filter.
                </div>
              ) : (
                cases.map((caseItem) => (
                  <Link
                    key={caseItem.id}
                    href={`/workspace/cases/${caseItem.id}`}
                    className="grid grid-cols-[1.4fr_0.7fr_0.7fr_0.7fr] gap-4 px-5 py-4 transition-colors hover:bg-slate-50"
                  >
                    <div>
                      <p className="font-semibold text-slate-900">{caseItem.title}</p>
                      <p className="mt-1 text-sm text-slate-500">
                        {caseItem.external_id ?? "No external reference"}
                      </p>
                    </div>
                    <div className="self-center">
                      <Badge
                        value={caseItem.status}
                        tone={statusTone[caseItem.status] ?? "neutral"}
                      />
                    </div>
                    <div className="self-center text-sm text-slate-600">
                      {formatEnumLabel(caseItem.priority)}
                    </div>
                    <div className="self-center text-sm text-slate-600">
                      {formatDateTime(caseItem.updated_at)}
                    </div>
                  </Link>
                ))
              )}
            </div>
          </div>
        </div>

        <div className="space-y-6">
          <div className="surface-card">
            <p className="text-xs font-semibold uppercase tracking-[0.28em] text-slate-500">
              Priority mix
            </p>
            <div className="mt-4 space-y-3">
              {prioritySnapshot.length === 0 ? (
                <p className="text-sm text-slate-500">Priority data will appear after loading.</p>
              ) : (
                prioritySnapshot.map(([priority, count]) => (
                  <div
                    key={priority}
                    className="flex items-center justify-between rounded-[1.4rem] border border-slate-200/70 bg-white/70 px-4 py-3"
                  >
                    <span className="text-sm font-medium text-slate-700">
                      {formatEnumLabel(priority)}
                    </span>
                    <span className="font-mono text-sm text-slate-500">{count}</span>
                  </div>
                ))
              )}
            </div>
          </div>

          <div className="surface-card">
            <p className="text-xs font-semibold uppercase tracking-[0.28em] text-slate-500">
              Operator notes
            </p>
            <div className="mt-4 rounded-[1.6rem] bg-[linear-gradient(135deg,#0f1720,#1f3144)] p-5 text-slate-50">
              <p className="text-sm font-medium text-slate-200">Suggested next iteration</p>
              <p className="mt-3 text-lg font-semibold tracking-[-0.03em]">
                Connect case detail pages to documents, comments and assistant workflows.
              </p>
              <p className="mt-3 text-sm leading-7 text-slate-300">
                This dashboard already reads real backend data. The next passes will expose
                document listings per case and an assistant that can answer with grounded
                references.
              </p>
            </div>

            <div className="mt-4 rounded-[1.6rem] border border-slate-200/80 bg-white/70 p-5">
              <p className="text-sm font-semibold text-slate-800">Upcoming due dates</p>
              <p className="mt-2 text-sm leading-7 text-slate-600">
                Cases with a deadline show up with human-friendly dates so the workspace already
                feels productized before the AI layer lands.
              </p>
              <div className="mt-4 rounded-2xl bg-slate-100/80 px-4 py-3 text-sm text-slate-700">
                Next due date on the board:{" "}
                <span className="font-semibold">
                  {cases.find((caseItem) => caseItem.due_date)?.title
                    ? `${cases.find((caseItem) => caseItem.due_date)?.title} · ${formatDate(
                        cases.find((caseItem) => caseItem.due_date)?.due_date,
                      )}`
                    : "No due dates available"}
                </span>
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}

function MetricCard({
  label,
  value,
  helper,
}: {
  label: string;
  value: number | undefined;
  helper: string;
}) {
  return (
    <article className="surface-card">
      <p className="text-xs font-semibold uppercase tracking-[0.28em] text-slate-500">{label}</p>
      <p className="mt-4 text-4xl font-semibold tracking-[-0.05em] text-slate-950">
        {typeof value === "number" ? value : "—"}
      </p>
      <p className="mt-2 text-sm leading-7 text-slate-600">{helper}</p>
    </article>
  );
}
