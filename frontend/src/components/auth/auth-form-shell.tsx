import Link from "next/link";
import type { ReactNode } from "react";

type AuthFormShellProps = {
  eyebrow: string;
  title: string;
  description: string;
  alternateCtaLabel: string;
  alternateHref: string;
  alternateText: string;
  children: ReactNode;
};

export function AuthFormShell({
  eyebrow,
  title,
  description,
  alternateCtaLabel,
  alternateHref,
  alternateText,
  children,
}: AuthFormShellProps) {
  return (
    <main className="mx-auto flex min-h-screen w-full max-w-7xl items-center px-6 py-10 lg:px-10">
      <div className="grid w-full gap-6 lg:grid-cols-[0.95fr_1.05fr]">
        <section className="surface-card flex flex-col justify-between gap-10 overflow-hidden bg-[linear-gradient(180deg,rgba(252,251,247,0.78),rgba(241,245,239,0.88))]">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.3em] text-slate-500">
              {eyebrow}
            </p>
            <h1 className="mt-4 text-5xl font-semibold tracking-[-0.06em] text-slate-950">
              {title}
            </h1>
            <p className="mt-5 max-w-xl text-base leading-8 text-slate-600">{description}</p>
          </div>

          <div className="rounded-[1.8rem] bg-slate-950 p-6 text-slate-50">
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
              Why this matters
            </p>
            <p className="mt-3 text-lg font-semibold tracking-[-0.03em]">
              The frontend is intentionally designed to expose the backend strengths you already
              built.
            </p>
            <p className="mt-3 text-sm leading-7 text-slate-300">
              Sessions, cases, reporting and document-heavy workflows are visible here instead of
              being buried in API routes.
            </p>
          </div>
        </section>

        <section className="surface-card flex items-center justify-center p-5 md:p-8">
          <div className="w-full max-w-xl">
            {children}
            <p className="mt-6 text-sm text-slate-600">
              {alternateText}{" "}
              <Link className="font-semibold text-slate-900 underline-offset-4 hover:underline" href={alternateHref}>
                {alternateCtaLabel}
              </Link>
            </p>
          </div>
        </section>
      </div>
    </main>
  );
}
