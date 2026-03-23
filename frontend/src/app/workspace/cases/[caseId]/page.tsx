export default function CaseDetailPage() {
  return (
    <div className="surface-card">
      <p className="text-xs font-semibold uppercase tracking-[0.3em] text-slate-500">
        Case detail
      </p>
      <h1 className="mt-3 text-3xl font-semibold tracking-[-0.04em] text-slate-950">
        Detailed case view is the next implementation step.
      </h1>
      <p className="mt-4 max-w-2xl text-base leading-7 text-slate-600">
        The routing shell is already in place. The next commit will wire this page to case data,
        comments, document listings and assistant interactions.
      </p>
    </div>
  );
}
