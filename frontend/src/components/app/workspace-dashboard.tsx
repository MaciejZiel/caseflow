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

  const prioritySnapshot = useMemo(() => {
    if (!summary) {
      return [];
    }
    return Object.entries(summary.priority_counts).sort((left, right) => right[1] - left[1]);
  }, [summary]);

  const nextDueCase = useMemo(
    () => cases.find((caseItem) => caseItem.due_date) ?? null,
    [cases],
  );

  return (
    <div className="space-y-6">
      <section className="grid gap-6 2xl:grid-cols-[1.18fr_0.82fr]">
        <div className="surface-panel-dark relative overflow-hidden p-6 text-slate-50 md:p-8">
          <div className="absolute right-[-5rem] top-[-3rem] h-52 w-52 rounded-full bg-orange-500/16 blur-3xl" />
          <div className="absolute bottom-[-5rem] left-[-2rem] h-48 w-48 rounded-full bg-teal-400/10 blur-3xl" />
          <div className="relative">
            <p className="text-[11px] font-semibold uppercase tracking-[0.32em] text-slate-400">
              Operations cockpit
            </p>
            <h2 className="mt-5 max-w-4xl text-4xl font-semibold tracking-[-0.07em] text-white md:text-6xl">
              See workload, unblock cases and move review work faster.
            </h2>
            <p className="mt-5 max-w-2xl text-base leading-8 text-slate-300">
              This dashboard turns the existing backend into a believable product surface:
              reporting, search, case creation and AI-ready operational context in one place.
            </p>

            <div className="mt-8 grid gap-4 md:grid-cols-3">
              <HeroMetric
                label="Active"
                value={summary?.active_cases}
                helper="Cases in motion right now"
              />
              <HeroMetric
                label="Due in 7 days"
                value={summary?.due_next_7_days}
                helper="Short-term review pressure"
              />
              <HeroMetric
                label="Overdue"
                value={summary?.overdue_cases}
                helper="Needs immediate attention"
              />
            </div>

            <form
              className="mt-8 grid gap-3 rounded-[1.7rem] border border-white/10 bg-white/6 p-4 lg:grid-cols-[minmax(0,1fr)_auto]"
              onSubmit={(event) => void handleSearch(event)}
            >
              <div>
                <label className="text-[11px] font-semibold uppercase tracking-[0.24em] text-slate-400">
                  Quick search
                </label>
                <input
                  className="mt-3 border-white/10 bg-white/8 text-white placeholder:text-slate-500"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Search by case title, external id or description"
                />
              </div>
              <div className="flex items-end">
                <Button className="w-full justify-center lg:w-auto" type="submit">
                  Search queue
                </Button>
              </div>
            </form>
          </div>
        </div>

        <div className="surface-card p-6 md:p-7">
          <div className="flex items-center justify-between gap-4">
            <div>
              <p className="eyebrow">New case</p>
              <h2 className="mt-3 text-3xl font-semibold tracking-[-0.05em] text-slate-950">
                Open work without leaving the dashboard
              </h2>
            </div>
            <span className="rounded-full border border-orange-200 bg-orange-50 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.2em] text-orange-900">
              Fast path
            </span>
          </div>

          <form className="mt-6 grid gap-4" onSubmit={handleCreateCase}>
            <div className="field-shell">
              <label className="field-label" htmlFor="new-case-title">
                Case title
              </label>
              <input
                id="new-case-title"
                value={newCaseTitle}
                onChange={(event) => setNewCaseTitle(event.target.value)}
                placeholder="Vehicle collision claim"
                required
              />
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
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
                placeholder="Summarize what operators should know before the first review pass."
              />
            </div>

            <Button disabled={isCreatingCase} fullWidth type="submit">
              {isCreatingCase ? "Creating case…" : "Create and open case"}
            </Button>
          </form>
        </div>
      </section>

      {errorMessage ? (
        <section className="surface-card border-rose-200 bg-rose-50/75">
          <p className="eyebrow text-rose-700">Dashboard notice</p>
          <p className="mt-3 text-base text-rose-900">{errorMessage}</p>
        </section>
      ) : null}

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="Total cases" value={summary?.total_cases} helper="All tracked work" />
        <MetricCard
          label="Archived"
          value={summary?.archived_cases}
          helper="Closed or retired cases"
        />
        <MetricCard
          label="Priority levels"
          value={prioritySnapshot.length}
          helper="Distinct urgency buckets in use"
        />
        <MetricCard
          label="Next due"
          value={nextDueCase ? formatDate(nextDueCase.due_date) : "No deadlines"}
          helper="Closest visible case deadline"
        />
      </section>

      <section className="grid gap-6 2xl:grid-cols-[1.16fr_0.84fr]">
        <div id="cases" className="surface-card p-6 md:p-7">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <p className="eyebrow">Case queue</p>
              <h2 className="mt-3 text-3xl font-semibold tracking-[-0.05em] text-slate-950">
                Cases worth opening next
              </h2>
              <p className="mt-3 max-w-2xl text-sm leading-7 text-slate-600">
                This queue is backed by real backend search and case data. It is the main proof
                that the product is more than a landing page around AI.
              </p>
            </div>
            <span className="rounded-full border border-slate-200 bg-white/70 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-700">
              {cases.length} loaded
            </span>
          </div>

          <div className="mt-6 grid gap-4">
            {loadState === "loading" ? (
              <EmptyQueueCard message="Loading cases from the workspace…" />
            ) : cases.length === 0 ? (
              <EmptyQueueCard message="No cases found for this filter." />
            ) : (
              cases.map((caseItem) => (
                <QueueRow key={caseItem.id} caseItem={caseItem} />
              ))
            )}
          </div>
        </div>

        <div className="space-y-6">
          <div className="surface-card p-6 md:p-7">
            <p className="eyebrow">Priority mix</p>
            <h2 className="mt-3 text-2xl font-semibold tracking-[-0.05em] text-slate-950">
              What the queue looks like right now
            </h2>
            <div className="mt-6 space-y-3">
              {prioritySnapshot.length === 0 ? (
                <p className="text-sm text-slate-500">Priority data will appear after loading.</p>
              ) : (
                prioritySnapshot.map(([priority, count]) => (
                  <PriorityStrip
                    key={priority}
                    count={count}
                    label={formatEnumLabel(priority)}
                    total={summary?.total_cases ?? 0}
                  />
                ))
              )}
            </div>
          </div>

          <div className="surface-panel-dark p-6 text-slate-50 md:p-7">
            <p className="text-[11px] font-semibold uppercase tracking-[0.28em] text-slate-400">
              Queue intelligence
            </p>
            <h2 className="mt-3 text-2xl font-semibold tracking-[-0.05em] text-white">
              Product story, not just metrics
            </h2>
            <p className="mt-4 text-sm leading-7 text-slate-300">
              The next interaction after this dashboard is a case workbench with documents,
              comments, audit trail and grounded assistant threads. That progression is what makes
              the app feel real.
            </p>
            <div className="mt-6 rounded-[1.5rem] border border-white/10 bg-white/6 p-4">
              <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-400">
                Earliest due case
              </p>
              <p className="mt-3 text-lg font-semibold text-white">
                {nextDueCase
                  ? `${nextDueCase.title} · ${formatDate(nextDueCase.due_date)}`
                  : "No due dates available"}
              </p>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}

function HeroMetric({
  label,
  value,
  helper,
}: {
  label: string;
  value: number | undefined;
  helper: string;
}) {
  return (
    <article className="rounded-[1.5rem] border border-white/10 bg-white/6 p-4">
      <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-400">
        {label}
      </p>
      <p className="mt-3 text-4xl font-semibold tracking-[-0.06em] text-white">
        {typeof value === "number" ? value : "—"}
      </p>
      <p className="mt-2 text-sm text-slate-300">{helper}</p>
    </article>
  );
}

function MetricCard({
  label,
  value,
  helper,
}: {
  label: string;
  value: number | string | undefined;
  helper: string;
}) {
  return (
    <article className="surface-card p-6">
      <p className="eyebrow">{label}</p>
      <p className="mt-4 text-4xl font-semibold tracking-[-0.05em] text-slate-950">
        {value ?? "—"}
      </p>
      <p className="mt-2 text-sm leading-7 text-slate-600">{helper}</p>
    </article>
  );
}

function EmptyQueueCard({ message }: { message: string }) {
  return (
    <div className="rounded-[1.7rem] border border-dashed border-slate-300 bg-white/50 px-5 py-8 text-sm text-slate-500">
      {message}
    </div>
  );
}

function QueueRow({ caseItem }: { caseItem: CaseRecord }) {
  return (
    <Link
      className="surface-panel grid gap-4 p-5 transition-transform hover:-translate-y-0.5"
      href={`/workspace/cases/${caseItem.id}`}
    >
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-3">
            <p className="text-xl font-semibold tracking-[-0.03em] text-slate-950">
              {caseItem.title}
            </p>
            <Badge value={caseItem.status} tone={statusTone[caseItem.status] ?? "neutral"} />
            <Badge value={caseItem.priority} />
          </div>
          <p className="mt-3 text-sm leading-7 text-slate-600">
            {caseItem.description || "No description has been added to this case yet."}
          </p>
        </div>

        <div className="rounded-[1.2rem] border border-slate-200 bg-white/70 px-3 py-2 text-sm font-semibold text-slate-700">
          Open case
        </div>
      </div>

      <div className="grid gap-3 md:grid-cols-3">
        <QueueMeta
          label="External reference"
          value={caseItem.external_id ?? "No external reference"}
        />
        <QueueMeta
          label="Due date"
          value={caseItem.due_date ? formatDate(caseItem.due_date) : "No deadline"}
        />
        <QueueMeta label="Last updated" value={formatDateTime(caseItem.updated_at)} />
      </div>
    </Link>
  );
}

function QueueMeta({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[1.1rem] bg-slate-100/85 px-4 py-3">
      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">
        {label}
      </p>
      <p className="mt-2 text-sm font-medium text-slate-800">{value}</p>
    </div>
  );
}

function PriorityStrip({
  label,
  count,
  total,
}: {
  label: string;
  count: number;
  total: number;
}) {
  const widthPercent = total > 0 ? Math.max((count / total) * 100, 8) : 8;

  return (
    <div className="rounded-[1.4rem] border border-slate-200/70 bg-white/75 p-4">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm font-semibold text-slate-800">{label}</p>
        <span className="font-mono text-sm text-slate-500">{count}</span>
      </div>
      <div className="mt-3 h-2 rounded-full bg-slate-100">
        <div
          className="h-2 rounded-full bg-[linear-gradient(90deg,#ff7a45,#c1421a)]"
          style={{ width: `${Math.min(widthPercent, 100)}%` }}
        />
      </div>
    </div>
  );
}
