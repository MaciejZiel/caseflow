"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { AuthFormShell } from "@/components/auth/auth-form-shell";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/auth-context";
import { ApiError } from "@/lib/api";

function slugifyOrganization(value: string) {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 120);
}

export default function RegisterPage() {
  const router = useRouter();
  const { register } = useAuth();
  const [organizationName, setOrganizationName] = useState("");
  const [organizationSlug, setOrganizationSlug] = useState("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const suggestedSlug = useMemo(
    () => (organizationSlug.trim() ? organizationSlug : slugifyOrganization(organizationName)),
    [organizationName, organizationSlug],
  );

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      setIsSubmitting(true);
      setErrorMessage(null);
      await register({
        organization_name: organizationName,
        organization_slug: suggestedSlug,
        first_name: firstName,
        last_name: lastName,
        email,
        password,
      });
      router.replace("/workspace");
    } catch (error) {
      setErrorMessage(
        error instanceof ApiError ? error.message : "Failed to create organization.",
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <AuthFormShell
      eyebrow="New organization"
      title="Create a workspace that actually looks deployable."
      description="Register an organization, issue the first owner session and enter the dashboard without leaving the product flow."
      alternateText="Already have access?"
      alternateCtaLabel="Sign in instead"
      alternateHref="/auth/login"
    >
      <form className="grid gap-5 md:grid-cols-2" onSubmit={handleSubmit}>
        <div className="surface-panel p-4 md:col-span-2">
          <p className="eyebrow">What happens next</p>
          <p className="mt-3 text-sm leading-7 text-slate-700">
            Creating the organization issues the first owner session immediately, so you land
            straight in the operations workspace without any separate activation flow.
          </p>
        </div>

        <div className="field-shell md:col-span-2">
          <label className="field-label" htmlFor="organizationName">
            Organization name
          </label>
          <input
            id="organizationName"
            value={organizationName}
            onChange={(event) => setOrganizationName(event.target.value)}
            placeholder="Acme Claims"
            required
          />
        </div>

        <div className="field-shell md:col-span-2">
          <label className="field-label" htmlFor="organizationSlug">
            Organization slug
          </label>
          <input
            id="organizationSlug"
            value={organizationSlug}
            onChange={(event) => setOrganizationSlug(slugifyOrganization(event.target.value))}
            placeholder="acme-claims"
            required
          />
          <p className="field-help">Slug preview: {suggestedSlug || "organization-slug"}</p>
        </div>

        <div className="field-shell">
          <label className="field-label" htmlFor="firstName">
            First name
          </label>
          <input
            id="firstName"
            value={firstName}
            onChange={(event) => setFirstName(event.target.value)}
            placeholder="Ada"
            required
          />
        </div>

        <div className="field-shell">
          <label className="field-label" htmlFor="lastName">
            Last name
          </label>
          <input
            id="lastName"
            value={lastName}
            onChange={(event) => setLastName(event.target.value)}
            placeholder="Lovelace"
            required
          />
        </div>

        <div className="field-shell md:col-span-2">
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

        <div className="field-shell md:col-span-2">
          <label className="field-label" htmlFor="password">
            Password
          </label>
          <input
            id="password"
            type="password"
            autoComplete="new-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            placeholder="At least 10 chars with upper, lower and digit"
            required
          />
        </div>

        {errorMessage ? <p className="field-error md:col-span-2">{errorMessage}</p> : null}

        <div className="md:col-span-2">
          <Button disabled={isSubmitting} fullWidth type="submit">
            {isSubmitting ? "Creating workspace…" : "Create and enter workspace"}
          </Button>
        </div>
      </form>
    </AuthFormShell>
  );
}
