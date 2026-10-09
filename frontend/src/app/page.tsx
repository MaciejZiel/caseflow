import Link from "next/link";

const trustSignals = [
  "multi-tenant auth and org isolation",
  "case and document workflows backed by a real API",
  "grounded assistant answers with citations",
  "audit, comments and operational history in one workspace",
];

const featureCards = [
  {
    eyebrow: "Case workbench",
    title: "One place for cases, evidence and AI help",
    description:
      "Operators move through a single workspace with case status, document uploads, comments, audit activity and grounded AI support.",
  },
  {
    eyebrow: "Grounded assistant",
    title: "Answers tied back to real case evidence",
    description:
      "Assistant threads are stored per case and return citations so the AI layer looks productized instead of speculative.",
  },
  {
    eyebrow: "Production posture",
    title: "Built on top of an already serious backend",
    description:
      "The frontend exposes auth, reporting, queue views and document-heavy workflows rather than hiding them behind swagger pages.",
  },
];

const outcomeCards = [
  {
    label: "Review throughput",
    value: "24 active",
    description: "Operators can spot queue pressure, overdue work and cases likely to block next.",
  },
  {
    label: "Evidence trail",
    value: "312 docs",
    description: "Documents, versions and audit events stay attached to the case instead of living in chat history.",
  },
  {
    label: "Grounded AI",
    value: "4 modes",
    description: "Summary, review assistant, next actions and general Q&A all work inside the same case context.",
  },
];

export default function Home() {
  return (
    <main className="relative isolate overflow-hidden">
      <div className="absolute inset-x-0 top-[-16rem] -z-10 h-[30rem] bg-[radial-gradient(circle_at_top,_rgba(255,122,69,0.22),_transparent_58%)]" />
      <div className="mx-auto flex w-full max-w-[1500px] flex-col gap-8 px-6 py-6 lg:px-10 lg:py-10">
        <header className="surface-card flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-center gap-4">
            <div className="surface-panel-dark flex h-14 w-14 items-center justify-center rounded-[1.4rem] text-lg font-semibold text-white">
              CF
            </div>
            <div>
              <p className="eyebrow">Caseflow AI</p>
              <p className="mt-2 text-sm text-slate-600">
                AI-assisted operations workspace for document-heavy case teams
              </p>
            </div>
          </div>

          <div className="flex flex-wrap gap-3">
            <Link className="button button-secondary" href="/auth/login">
              Sign in
            </Link>
            <Link className="button button-primary" href="/auth/register">
              Launch workspace
            </Link>
          </div>
        </header>

        <section className="grid gap-6 xl:grid-cols-[1.08fr_0.92fr]">
          <div className="surface-panel-dark relative overflow-hidden p-8 text-slate-50 md:p-10">
            <div className="absolute right-[-6rem] top-[-5rem] h-52 w-52 rounded-full bg-orange-500/18 blur-3xl" />
            <div className="absolute bottom-[-8rem] left-[-3rem] h-56 w-56 rounded-full bg-teal-400/12 blur-3xl" />
            <div className="relative">
              <p className="text-[11px] font-semibold uppercase tracking-[0.34em] text-slate-400">
                Portfolio-grade full stack product
              </p>
              <h1 className="mt-6 max-w-4xl text-5xl font-semibold leading-[0.94] tracking-[-0.08em] text-white md:text-7xl">
                Case operations that look and feel like a real SaaS product.
              </h1>
              <p className="mt-6 max-w-2xl text-lg leading-8 text-slate-300">
                Caseflow AI layers a modern workbench on top of a serious backend so auth,
                reporting, evidence handling and grounded AI are visible the moment someone opens
                the app.
              </p>

              <div className="mt-8 flex flex-wrap gap-3">
                <Link className="button button-primary" href="/workspace">
                  Open demo workspace
                </Link>
                <Link className="button button-secondary border-white/10 bg-white/6 text-white" href="/auth/register">
                  Create organization
                </Link>
              </div>

              <div className="mt-10 grid gap-3 md:grid-cols-2">
                {trustSignals.map((signal) => (
                  <div
                    key={signal}
                    className="rounded-[1.35rem] border border-white/10 bg-white/6 px-4 py-4 text-sm font-medium text-slate-200"
                  >
                    {signal}
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="grid gap-6">
            <div className="surface-card p-6 md:p-7">
              <div className="flex items-center justify-between">
                <div>
                  <p className="eyebrow">Live snapshot</p>
                  <h2 className="mt-3 text-3xl font-semibold tracking-[-0.05em] text-slate-950">
                    Review desk
                  </h2>
                </div>
                <span className="rounded-full border border-teal-200 bg-teal-50 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.2em] text-teal-800">
                  Deployed UX
                </span>
              </div>

              <div className="mt-6 grid gap-4 sm:grid-cols-2">
                {outcomeCards.map((card) => (
                  <article
                    key={card.label}
                    className="surface-panel p-5 first:sm:col-span-2"
                  >
                    <p className="eyebrow">{card.label}</p>
                    <p className="mt-3 text-4xl font-semibold tracking-[-0.06em] text-slate-950">
                      {card.value}
                    </p>
                    <p className="mt-3 text-sm leading-7 text-slate-600">{card.description}</p>
                  </article>
                ))}
              </div>
            </div>

            <div className="surface-card p-6 md:p-7">
              <div className="flex items-center justify-between">
                <div>
                  <p className="eyebrow">Assistant thread</p>
                  <h2 className="mt-3 text-2xl font-semibold tracking-[-0.05em] text-slate-950">
                    Grounded case guidance
                  </h2>
                </div>
                <span className="rounded-full bg-orange-100 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.2em] text-orange-900">
                  Review mode
                </span>
              </div>

              <div className="mt-5 rounded-[1.8rem] bg-[linear-gradient(180deg,#111b28,#0a121d)] p-5 text-slate-50 shadow-[0_28px_60px_-36px_rgba(16,24,37,0.9)]">
                <p className="text-sm font-medium text-slate-300">
                  What is still missing before this case can be approved?
                </p>
                <div className="mt-4 rounded-[1.4rem] border border-white/8 bg-white/5 p-4">
                  <p className="text-sm leading-7 text-slate-200">
                    The latest evidence suggests two blocking gaps: the claimant statement is still
                    unsigned and the repair estimate does not include insurer approval metadata.
                    The strongest references are <span className="font-semibold text-white">statement-v2.txt</span> and{" "}
                    <span className="font-semibold text-white">repair-estimate-march.pdf</span>.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="grid gap-5 lg:grid-cols-3">
          {featureCards.map((feature) => (
            <article key={feature.title} className="surface-card p-6 md:p-7">
              <p className="eyebrow">{feature.eyebrow}</p>
              <h2 className="mt-4 text-3xl font-semibold tracking-[-0.05em] text-slate-950">
                {feature.title}
              </h2>
              <p className="mt-4 text-base leading-8 text-slate-600">{feature.description}</p>
            </article>
          ))}
        </section>
      </div>
    </main>
  );
}
