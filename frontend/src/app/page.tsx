import Link from "next/link";

const featureCards = [
  {
    eyebrow: "Operations-first AI",
    title: "Case-based workspace",
    description:
      "Track document-heavy cases with status, owners, due dates, history and a structure that fits real operations work.",
  },
  {
    eyebrow: "Grounded workflows",
    title: "Documents with provenance",
    description:
      "Uploads, version history, extracted payloads and review steps make the app look like a product, not a toy chatbot.",
  },
  {
    eyebrow: "Full-stack baseline",
    title: "FastAPI backend + Next frontend",
    description:
      "The frontend is built to sit on top of the existing API surface and showcase auth, reporting, cases and assistant UX.",
  },
];

const productSignals = [
  "organization auth and session management",
  "case reporting and recent workload overview",
  "document uploads, reviews and processing history",
  "AI assistant entry point designed around cases, not generic chat",
];

export default function Home() {
  return (
    <main className="relative isolate overflow-hidden">
      <div className="absolute inset-x-0 top-[-16rem] -z-10 h-[28rem] bg-[radial-gradient(circle_at_top,_rgba(201,109,45,0.22),_transparent_58%)]" />
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-16 px-6 py-10 lg:px-10 lg:py-14">
        <header className="flex items-center justify-between rounded-full border border-white/50 bg-white/70 px-5 py-3 shadow-[0_18px_60px_-32px_rgba(15,23,32,0.35)] backdrop-blur">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-[linear-gradient(135deg,#0f1720,#27445d)] text-sm font-semibold uppercase tracking-[0.24em] text-white">
              CF
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.28em] text-slate-500">
                Caseflow AI
              </p>
              <p className="text-sm text-slate-700">Case operations for document-heavy teams</p>
            </div>
          </div>
          <div className="flex gap-3">
            <Link className="button button-secondary" href="/auth/login">
              Sign in
            </Link>
            <Link className="button button-primary" href="/auth/register">
              Launch workspace
            </Link>
          </div>
        </header>

        <section className="grid gap-10 lg:grid-cols-[1.2fr_0.8fr] lg:items-end">
          <div className="space-y-8">
            <div className="space-y-4">
              <span className="inline-flex rounded-full border border-amber-400/50 bg-amber-100/80 px-4 py-1 text-xs font-semibold uppercase tracking-[0.28em] text-amber-900">
                Multi-tenant case intelligence
              </span>
              <h1 className="max-w-4xl text-5xl font-semibold leading-[1.02] tracking-[-0.05em] text-slate-950 md:text-7xl">
                Turn case management into something operators can actually trust.
              </h1>
              <p className="max-w-2xl text-lg leading-8 text-slate-600 md:text-xl">
                Caseflow AI wraps a production-style backend with a modern workspace for
                reviewing cases, handling documents and layering grounded AI help on top of
                existing operational flows.
              </p>
            </div>

            <div className="flex flex-wrap gap-3">
              <Link className="button button-primary" href="/auth/register">
                Create organization
              </Link>
              <Link className="button button-secondary" href="/workspace">
                Open dashboard
              </Link>
            </div>

            <div className="grid gap-3 md:grid-cols-2">
              {productSignals.map((signal) => (
                <div key={signal} className="surface-card surface-card-muted">
                  <p className="text-sm font-medium text-slate-700">{signal}</p>
                </div>
              ))}
            </div>
          </div>

          <div className="surface-card relative overflow-hidden">
            <div className="absolute inset-x-0 top-0 h-28 bg-[radial-gradient(circle_at_top,_rgba(95,148,116,0.18),_transparent_70%)]" />
            <div className="relative space-y-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.28em] text-slate-500">
                    Demo snapshot
                  </p>
                  <h2 className="mt-2 text-2xl font-semibold text-slate-950">
                    Review desk overview
                  </h2>
                </div>
                <span className="rounded-full bg-emerald-100 px-3 py-1 text-xs font-semibold uppercase tracking-[0.22em] text-emerald-900">
                  Live-ready
                </span>
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <div className="rounded-3xl border border-slate-200/80 bg-white/85 p-5 shadow-[0_12px_24px_-22px_rgba(15,23,32,0.45)]">
                  <p className="text-sm text-slate-500">Open cases</p>
                  <p className="mt-3 text-4xl font-semibold tracking-[-0.05em] text-slate-950">
                    24
                  </p>
                  <p className="mt-2 text-sm text-emerald-700">+5 due this week</p>
                </div>
                <div className="rounded-3xl border border-slate-200/80 bg-white/85 p-5 shadow-[0_12px_24px_-22px_rgba(15,23,32,0.45)]">
                  <p className="text-sm text-slate-500">Review alerts</p>
                  <p className="mt-3 text-4xl font-semibold tracking-[-0.05em] text-slate-950">
                    7
                  </p>
                  <p className="mt-2 text-sm text-amber-700">2 waiting for operator action</p>
                </div>
              </div>

              <div className="rounded-[2rem] border border-slate-200/80 bg-slate-950 p-5 text-slate-50 shadow-[0_22px_50px_-28px_rgba(15,23,32,0.8)]">
                <div className="flex items-center justify-between">
                  <p className="text-sm font-medium text-slate-200">Ask Caseflow AI</p>
                  <span className="rounded-full bg-white/10 px-3 py-1 text-[11px] uppercase tracking-[0.2em] text-slate-300">
                    Grounded mode
                  </span>
                </div>
                <p className="mt-4 text-sm leading-7 text-slate-300">
                  Summarize the missing documents and cite the latest evidence for claim
                  <span className="font-semibold text-white"> CLM-2026-1049</span>.
                </p>
                <div className="mt-5 rounded-2xl border border-white/10 bg-white/5 p-4 text-sm leading-7 text-slate-200">
                  Latest version notes point to an unsigned repair estimate and a missing
                  claimant statement. Document versions `invoice_march.pdf` and
                  `statement-v2.txt` are the strongest references for the next action.
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="grid gap-5 lg:grid-cols-3">
          {featureCards.map((feature) => (
            <article key={feature.title} className="surface-card">
              <p className="text-xs font-semibold uppercase tracking-[0.26em] text-slate-500">
                {feature.eyebrow}
              </p>
              <h2 className="mt-4 text-2xl font-semibold tracking-[-0.03em] text-slate-950">
                {feature.title}
              </h2>
              <p className="mt-3 text-base leading-7 text-slate-600">{feature.description}</p>
            </article>
          ))}
        </section>
      </div>
    </main>
  );
}
