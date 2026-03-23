"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/auth-context";
import { initials } from "@/lib/format";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/workspace", label: "Operations", match: "/workspace" },
  { href: "/workspace#cases", label: "Case queue", match: "/workspace/cases" },
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

  const currentSection = pathname.startsWith("/workspace/cases")
    ? "Case Workbench"
    : "Operations Dashboard";

  return (
    <div className="mx-auto min-h-screen w-full max-w-[1600px] px-4 py-4 sm:px-6 lg:px-8 lg:py-6">
      <div className="grid gap-4 lg:grid-cols-[290px_minmax(0,1fr)]">
        <aside className="surface-panel-dark p-5 text-slate-50 lg:sticky lg:top-6 lg:h-[calc(100vh-3rem)]">
          <div className="flex h-full flex-col">
            <div className="flex items-center gap-4">
              <div className="flex h-14 w-14 items-center justify-center rounded-[1.5rem] border border-white/10 bg-white/6 text-lg font-semibold">
                CF
              </div>
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-[0.28em] text-slate-400">
                  Caseflow AI
                </p>
                <p className="mt-1 text-sm text-slate-300">Operational intelligence desk</p>
              </div>
            </div>

            <div className="mt-8 rounded-[1.6rem] border border-white/10 bg-white/6 p-4">
              <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-400">
                Workspace
              </p>
              <h1 className="mt-3 text-2xl font-semibold tracking-[-0.04em]">
                {session.organization.name}
              </h1>
              <p className="mt-2 text-sm leading-6 text-slate-300">
                `{session.organization.slug}` · {session.membership.role.toLowerCase()} access
              </p>
            </div>

            <nav className="mt-8 grid gap-2">
              {navItems.map((item) => {
                const isActive =
                  item.match === "/workspace"
                    ? pathname === "/workspace"
                    : pathname.startsWith(item.match);

                return (
                  <Link
                    key={item.href}
                    className={cn(
                      "rounded-[1.2rem] border px-4 py-3 text-sm font-semibold transition-all",
                      isActive
                        ? "border-orange-300/50 bg-gradient-to-r from-orange-500 to-orange-600 text-white shadow-[0_18px_36px_-24px_rgba(255,122,69,0.85)]"
                        : "border-white/8 bg-white/4 text-slate-200 hover:border-white/16 hover:bg-white/7",
                    )}
                    href={item.href}
                  >
                    {item.label}
                  </Link>
                );
              })}
            </nav>

            <div className="mt-8 rounded-[1.6rem] border border-white/10 bg-[linear-gradient(180deg,rgba(255,255,255,0.08),rgba(255,255,255,0.03))] p-4">
              <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-400">
                Signed in as
              </p>
              <div className="mt-3 flex items-center gap-3">
                <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-white/10 font-semibold">
                  {initials(session.user.first_name, session.user.last_name)}
                </div>
                <div>
                  <p className="text-sm font-semibold text-white">
                    {session.user.first_name} {session.user.last_name}
                  </p>
                  <p className="text-sm text-slate-300">{session.user.email}</p>
                </div>
              </div>
            </div>

            <div className="mt-auto">
              <Button className="w-full justify-center" variant="ghost" onClick={handleLogout}>
                Sign out
              </Button>
            </div>
          </div>
        </aside>

        <div className="flex min-w-0 flex-col gap-4">
          <header className="surface-card flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <p className="eyebrow">Live workspace</p>
              <h2 className="mt-3 text-3xl font-semibold tracking-[-0.05em] text-slate-950">
                {currentSection}
              </h2>
              <p className="mt-2 max-w-2xl text-sm leading-7 text-slate-600">
                Product-grade visibility for case operations, evidence review and grounded AI
                assistance.
              </p>
            </div>
            <div className="surface-panel grid gap-3 px-4 py-4 text-sm text-slate-700 sm:grid-cols-2">
              <div>
                <p className="eyebrow">Tenant</p>
                <p className="mt-2 font-semibold text-slate-950">{session.organization.slug}</p>
              </div>
              <div>
                <p className="eyebrow">Today</p>
                <p className="mt-2 font-semibold text-slate-950">
                  {new Intl.DateTimeFormat("en", {
                    dateStyle: "long",
                  }).format(new Date())}
                </p>
              </div>
            </div>
          </header>

          <main className="min-w-0 flex-1">{children}</main>
        </div>
      </div>
    </div>
  );
}
