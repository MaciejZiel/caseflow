"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/auth-context";
import { formatEnumLabel } from "@/lib/format";

type AppShellProps = {
  children: ReactNode;
};

export function AppShell({ children }: AppShellProps) {
  const router = useRouter();
  const { logout, session } = useAuth();

  const handleLogout = () => {
    logout();
    router.replace("/auth/login");
  };

  if (!session) {
    return null;
  }

  return (
    <div className="min-h-screen">
      <header className="border-b border-line bg-surface">
        <div className="mx-auto flex max-w-[1400px] flex-wrap items-center gap-x-6 gap-y-2 px-4 py-2.5 sm:px-6">
          <Link className="font-semibold" href="/workspace">
            CaseFlow
          </Link>
          <span className="text-muted">
            {session.organization.name}
            <span className="ml-2 hidden font-mono text-xs sm:inline">
              {session.organization.slug}
            </span>
          </span>
          <div className="ml-auto flex items-center gap-3">
            <span className="hidden text-muted md:inline">
              {session.user.first_name} {session.user.last_name} ·{" "}
              {formatEnumLabel(session.membership.role.toLowerCase())}
            </span>
            <Button variant="secondary" onClick={handleLogout}>
              Sign out
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-[1400px] px-4 py-5 sm:px-6">{children}</main>
    </div>
  );
}
