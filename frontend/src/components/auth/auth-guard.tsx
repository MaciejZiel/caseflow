"use client";

import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { useAuth } from "@/context/auth-context";

type AuthGuardProps = {
  children: ReactNode;
};

export function AuthGuard({ children }: AuthGuardProps) {
  const router = useRouter();
  const { status } = useAuth();

  useEffect(() => {
    if (status === "anonymous") {
      router.replace("/auth/login");
    }
  }, [router, status]);

  if (status === "loading") {
    return (
      <div className="mx-auto flex min-h-[50vh] max-w-7xl items-center justify-center px-6">
        <div className="surface-card max-w-md text-center">
          <p className="text-xs font-semibold uppercase tracking-[0.26em] text-slate-500">
            Authenticating
          </p>
          <h1 className="mt-3 text-3xl font-semibold tracking-[-0.04em] text-slate-950">
            Restoring your workspace
          </h1>
          <p className="mt-3 text-base leading-7 text-slate-600">
            We are loading the current organization context before rendering the dashboard.
          </p>
        </div>
      </div>
    );
  }

  if (status === "anonymous") {
    return null;
  }

  return <>{children}</>;
}
