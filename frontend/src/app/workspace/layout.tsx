import type { ReactNode } from "react";

import { AppShell } from "@/components/app/app-shell";
import { AuthGuard } from "@/components/auth/auth-guard";

type WorkspaceLayoutProps = {
  children: ReactNode;
};

export default function WorkspaceLayout({ children }: WorkspaceLayoutProps) {
  return (
    <AuthGuard>
      <AppShell>{children}</AppShell>
    </AuthGuard>
  );
}
