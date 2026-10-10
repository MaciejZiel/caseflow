"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Badge, priorityTone, statusTone } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/auth-context";
import { ApiError, createCase, getCaseSummary, listCases } from "@/lib/api";
import { formatDate, formatDateTime, formatEnumLabel } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { CaseRecord, CaseSummaryReport } from "@/lib/types";

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
        error instanceof ApiError ? error.message : "Could not load cases.",
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

  async function handleSearch(event?: React.FormEvent<HTMLFormElement>) {
    event?.preventDefault();
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
      setErrorMessage(null);
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

  const statusBreakdown = useMemo(() => sortedEntries(summary?.status_counts), [summary]);
  const priorityBreakdown = useMemo(() => sortedEntries(summary?.priority_counts), [summary]);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-x-8 gap-y-3">
        <h1 className="text-xl font-semibold">Cases</h1>
        <dl className="flex flex-wrap gap-x-6 gap-y-1">
          <Stat label="Total" value={summary?.total_cases} />
          <Stat label="Active" value={summary?.active_cases} />
          <Stat label="Due in 7 days" value={summary?.due_next_7_days} />
          <Stat label="Overdue" value={summary?.overdue_cases} alert />
          <Stat label="Archived" value={summary?.archived_cases} />
        </dl>
      </div>

      {errorMessage ? <p className="notice-error">{errorMessage}</p> : null}

      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_300px]">
        <section id="cases" className="panel min-w-0">
          <form
            className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-2.5"
            onSubmit={(event) => void handleSearch(event)}
            role="search"
          >
            <label className="sr-only" htmlFor="case-search">
              Search cases
            </label>
            <input
              id="case-search"
              className="min-w-0 flex-1"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search title, reference or description"
            />
            <Button type="submit" variant="secondary">
              Search
            </Button>
            <span className="count ml-auto">
              {loadState === "ready" ? `${cases.length} shown` : null}
            </span>
          </form>

          {loadState === "loading" ? (
            <p className="empty">Loading cases…</p>
          ) : cases.length === 0 ? (
            <p className="empty">
              {query.trim() ? "No cases match this search." : "No cases yet. Create one to get started."}
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="data-table sm:min-w-[720px]">
                <thead>
                  <tr>
                    <th>Case</th>
                    <th className="hidden sm:table-cell">Reference</th>
                    <th className="hidden sm:table-cell">Status</th>
                    <th className="hidden sm:table-cell">Priority</th>
                    <th className="hidden sm:table-cell">Due</th>
                    <th className="hidden sm:table-cell">Updated</th>
                  </tr>
                </thead>
                <tbody>
                  {cases.map((caseItem) => (
                    <CaseRow key={caseItem.id} caseItem={caseItem} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <aside className="space-y-5">
          <section className="panel">
            <div className="panel-head">
              <h2 className="panel-title">New case</h2>
            </div>
            <form className="panel-body grid gap-3" onSubmit={handleCreateCase}>
              <div className="field-shell">
                <label className="field-label" htmlFor="new-case-title">
                  Case title
                </label>
                <input
                  id="new-case-title"
                  value={newCaseTitle}
                  onChange={(event) => setNewCaseTitle(event.target.value)}
                  required
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="field-shell">
                  <label className="field-label" htmlFor="new-case-external-id">
                    External reference
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
                  Intake note
                </label>
                <textarea
                  id="new-case-description"
                  value={newCaseDescription}
                  onChange={(event) => setNewCaseDescription(event.target.value)}
                />
              </div>

              <Button disabled={isCreatingCase} fullWidth type="submit">
                {isCreatingCase ? "Creating case…" : "Create and open case"}
              </Button>
            </form>
          </section>

          <Breakdown title="By status" entries={statusBreakdown} total={summary?.total_cases} />
          <Breakdown title="By priority" entries={priorityBreakdown} total={summary?.total_cases} />
        </aside>
      </div>
    </div>
  );
}

function sortedEntries(counts: Record<string, number> | undefined) {
  return Object.entries(counts ?? {}).sort((left, right) => right[1] - left[1]);
}

function isOverdue(caseItem: CaseRecord) {
  if (!caseItem.due_date || caseItem.archived_at) {
    return false;
  }
  return new Date(caseItem.due_date).getTime() < new Date().setHours(0, 0, 0, 0);
}

function Stat({ label, value, alert = false }: { label: string; value?: number; alert?: boolean }) {
  const highlighted = alert && typeof value === "number" && value > 0;
  return (
    <div className="flex items-baseline gap-1.5">
      <dt className="text-muted">{label}</dt>
      <dd className={cn("text-base font-semibold", highlighted && "text-red-700")}>
        {typeof value === "number" ? value : "–"}
      </dd>
    </div>
  );
}

function CaseRow({ caseItem }: { caseItem: CaseRecord }) {
  return (
    <tr>
      <td>
        <Link
          className="font-medium text-accent-ink hover:underline"
          href={`/workspace/cases/${caseItem.id}`}
        >
          {caseItem.title}
        </Link>
        {caseItem.description ? (
          <p className="mt-0.5 text-muted sm:max-w-[26rem] sm:truncate">{caseItem.description}</p>
        ) : null}
        <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-xs text-muted sm:hidden">
          <Badge value={caseItem.status} tone={statusTone[caseItem.status] ?? "neutral"} />
          <Badge value={caseItem.priority} tone={priorityTone[caseItem.priority] ?? "neutral"} />
          {caseItem.due_date ? <span>Due {formatDate(caseItem.due_date)}</span> : null}
        </div>
      </td>
      <td className="hidden whitespace-nowrap font-mono text-xs text-muted sm:table-cell">
        {caseItem.external_id ?? "–"}
      </td>
      <td className="hidden sm:table-cell">
        <Badge value={caseItem.status} tone={statusTone[caseItem.status] ?? "neutral"} />
      </td>
      <td className="hidden sm:table-cell">
        <Badge value={caseItem.priority} tone={priorityTone[caseItem.priority] ?? "neutral"} />
      </td>
      <td className={cn("hidden whitespace-nowrap sm:table-cell", isOverdue(caseItem) && "font-medium text-red-700")}>
        {caseItem.due_date ? formatDate(caseItem.due_date) : "–"}
      </td>
      <td className="hidden whitespace-nowrap text-muted sm:table-cell" title={formatDateTime(caseItem.updated_at)}>
        {formatDate(caseItem.updated_at)}
      </td>
    </tr>
  );
}

function Breakdown({
  title,
  entries,
  total,
}: {
  title: string;
  entries: [string, number][];
  total: number | undefined;
}) {
  return (
    <section className="panel">
      <div className="panel-head">
        <h2 className="panel-title">{title}</h2>
      </div>
      {entries.length === 0 ? (
        <p className="empty">No cases yet.</p>
      ) : (
        <ul className="panel-body space-y-2.5">
          {entries.map(([key, count]) => (
            <li key={key}>
              <div className="flex justify-between gap-3">
                <span>{formatEnumLabel(key)}</span>
                <span className="font-medium">{count}</span>
              </div>
              <div className="mt-1 h-1 rounded-full bg-slate-100">
                <div
                  className="h-1 rounded-full bg-accent"
                  style={{ width: `${total ? (count / total) * 100 : 0}%` }}
                />
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
