import Link from "next/link";
import type { ReactNode } from "react";

type AuthFormShellProps = {
  title: string;
  alternateCtaLabel: string;
  alternateHref: string;
  alternateText: string;
  children: ReactNode;
};

export function AuthFormShell({
  title,
  alternateCtaLabel,
  alternateHref,
  alternateText,
  children,
}: AuthFormShellProps) {
  return (
    <main className="flex min-h-screen flex-col items-center px-4 py-12 sm:py-20">
      <div className="w-full max-w-md">
        <p className="text-sm font-semibold">CaseFlow</p>
        <h1 className="mt-6 text-2xl font-semibold">{title}</h1>
        <div className="panel mt-5 p-5">{children}</div>
        <p className="mt-4 text-sm text-muted">
          {alternateText}{" "}
          <Link className="font-medium text-accent hover:underline" href={alternateHref}>
            {alternateCtaLabel}
          </Link>
        </p>
      </div>
    </main>
  );
}
