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
    <main className="mx-auto flex min-h-screen w-full max-w-[1500px] items-center px-6 py-10 lg:px-10">
      <div className="grid w-full gap-6 lg:grid-cols-[1.02fr_0.98fr]">
        <section className="surface-panel-dark relative overflow-hidden p-8 text-slate-50 md:p-10">
          <div className="absolute inset-x-0 top-0 h-40 bg-[radial-gradient(circle_at_top,_rgba(255,122,69,0.38),_transparent_66%)]" />
          <div className="absolute bottom-[-4rem] right-[-4rem] h-56 w-56 rounded-full bg-teal-400/10 blur-3xl" />
          <div className="relative flex h-full flex-col justify-between gap-12">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.32em] text-slate-400">
                {eyebrow}
              </p>
              <h1 className="mt-5 max-w-xl text-5xl font-semibold tracking-[-0.07em] text-white md:text-6xl">
                {title}
              </h1>
              <p className="mt-6 max-w-xl text-base leading-8 text-slate-300">{description}</p>
            </div>

            <div className="grid gap-4 md:grid-cols-3">
              <SignalCard label="API" value="Auth + cases" />
              <SignalCard label="AI" value="Grounded threads" />
              <SignalCard label="Ops" value="Review-ready UI" />
            </div>

            <div className="rounded-[1.8rem] border border-white/10 bg-white/6 p-6">
              <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-slate-400">
                Why this matters
              </p>
              <p className="mt-3 text-lg font-semibold tracking-[-0.03em] text-white">
                The interface should sell the product story in under thirty seconds.
              </p>
              <p className="mt-3 text-sm leading-7 text-slate-300">
                This app needs to feel like a real operations product with AI built into casework,
                not a form wrapper around endpoints.
              </p>
            </div>
          </div>
        </section>

        <section className="surface-card flex items-center justify-center p-5 md:p-8">
          <div className="w-full max-w-xl">
            {children}
            <p className="mt-6 text-sm text-slate-600">
              {alternateText}{" "}
              <Link
                className="font-semibold text-slate-900 underline-offset-4 hover:underline"
                href={alternateHref}
              >
                {alternateCtaLabel}
              </Link>
            </p>
          </div>
        </section>
      </div>
    </main>
  );
}

function SignalCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[1.5rem] border border-white/10 bg-white/6 px-4 py-4">
      <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-400">
        {label}
      </p>
      <p className="mt-3 text-lg font-semibold tracking-[-0.03em] text-white">{value}</p>
    </div>
  );
}
