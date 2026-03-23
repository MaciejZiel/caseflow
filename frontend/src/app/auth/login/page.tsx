"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { AuthFormShell } from "@/components/auth/auth-form-shell";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/auth-context";
import { ApiError } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [organizationSlug, setOrganizationSlug] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      setIsSubmitting(true);
      setErrorMessage(null);
      await login({
        email,
        password,
        organization_slug: organizationSlug.trim() || undefined,
      });
      router.replace("/workspace");
    } catch (error) {
      setErrorMessage(error instanceof ApiError ? error.message : "Sign in failed.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <AuthFormShell
      eyebrow="Workspace access"
      title="Sign in to your operations desk."
      description="Authenticate against the existing CaseFlow backend and restore the current organization context."
      alternateText="Need a fresh organization?"
      alternateCtaLabel="Create one"
      alternateHref="/auth/register"
    >
      <form className="space-y-5" onSubmit={handleSubmit}>
        <div className="field-shell">
          <label className="field-label" htmlFor="email">
            Email
          </label>
          <input
            id="email"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="ada@example.com"
            required
          />
        </div>

        <div className="field-shell">
          <label className="field-label" htmlFor="organizationSlug">
            Workspace slug
          </label>
          <input
            id="organizationSlug"
            value={organizationSlug}
            onChange={(event) => setOrganizationSlug(event.target.value)}
            placeholder="acme-claims"
          />
          <p className="field-help">Optional, but useful if the same email exists in multiple orgs.</p>
        </div>

        <div className="field-shell">
          <label className="field-label" htmlFor="password">
            Password
          </label>
          <input
            id="password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            placeholder="Your secure password"
            required
          />
        </div>

        {errorMessage ? <p className="field-error">{errorMessage}</p> : null}

        <Button disabled={isSubmitting} fullWidth type="submit">
          {isSubmitting ? "Signing in…" : "Sign in"}
        </Button>
      </form>
    </AuthFormShell>
  );
}
