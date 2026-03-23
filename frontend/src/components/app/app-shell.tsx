"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/auth-context";
import { initials } from "@/lib/format";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/workspace", label: "Dashboard" },
  { href: "/workspace#cases", label: "Cases" },
];

type AppShellProps = {
  children: ReactNode;
};

export function AppShell({ children }: AppShellProps) {
  const pathname = usePathname();
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
    <div className="mx-auto flex min-h-screen w-full max-w-7xl flex-col px-4 py-4 sm:px-6 lg:px-8">
      <header className="surface-card mb-6 flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex items-center gap-4">
          <div className="flex h-14 w-14 items-center justify-center rounded-[1.4rem] bg-[linear-gradient(135deg,#0f1720,#27445d)] text-lg font-semibold text-white">
            {initials(session.user.first_name, session.user.last_name)}
          </div>
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.3em] text-slate-500">
              {session.organization.slug}
            </p>
            <h1 className="mt-1 text-2xl font-semibold tracking-[-0.04em] text-slate-950">
              {session.organization.name}
            </h1>
            <p className="mt-1 text-sm text-slate-600">
              Signed in as {session.user.first_name} {session.user.last_name} ·{" "}
              {session.membership.role.toLowerCase()}
            </p>
          </div>
        </div>

        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <nav className="flex flex-wrap gap-2">
            {navItems.map((item) => (
              <Link
                key={item.href}
                className={cn(
                  "button text-sm",
                  pathname === "/workspace" && item.href === "/workspace"
                    ? "button-primary"
                    : "button-secondary",
                )}
                href={item.href}
              >
                {item.label}
              </Link>
            ))}
          </nav>
          <Button variant="ghost" onClick={handleLogout}>
            Sign out
          </Button>
        </div>
      </header>
      <div className="flex-1">{children}</div>
    </div>
  );
}
