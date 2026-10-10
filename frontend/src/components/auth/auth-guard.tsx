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
    return <p className="px-4 py-10 text-center text-muted">Loading workspace…</p>;
  }

  if (status === "anonymous") {
    return null;
  }

  return <>{children}</>;
}
