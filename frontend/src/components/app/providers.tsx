"use client";

import type { ReactNode } from "react";

import { AuthProvider } from "@/context/auth-context";

type ProvidersProps = {
  children: ReactNode;
};

export function Providers({ children }: ProvidersProps) {
  return <AuthProvider>{children}</AuthProvider>;
}
