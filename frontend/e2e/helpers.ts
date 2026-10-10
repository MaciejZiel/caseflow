import { expect, type Page } from "@playwright/test";

type WorkspaceCredentials = {
  organizationName: string;
  organizationSlug: string;
  firstName: string;
  lastName: string;
  email: string;
  password: string;
};

export function createWorkspaceCredentials(prefix: string): WorkspaceCredentials {
  const suffix = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  return {
    organizationName: `${prefix} ${suffix}`,
    organizationSlug: `${prefix.toLowerCase().replace(/[^a-z0-9]+/g, "-")}-${suffix}`.slice(
      0,
      120,
    ),
    firstName: "Ada",
    lastName: "Lovelace",
    email: `${prefix.toLowerCase().replace(/[^a-z0-9]+/g, ".")}.${suffix}@example.com`,
    password: "StrongPass123",
  };
}

export async function registerWorkspace(page: Page, credentials: WorkspaceCredentials) {
  await page.goto("/auth/register");

  await page.getByLabel("Organization name").fill(credentials.organizationName);
  await page.getByLabel("Organization slug").fill(credentials.organizationSlug);
  await page.getByLabel("First name").fill(credentials.firstName);
  await page.getByLabel("Last name").fill(credentials.lastName);
  await page.getByLabel("Email").fill(credentials.email);
  await page.getByLabel("Password").fill(credentials.password);

  await page.getByRole("button", { name: "Create organization" }).click();
  await expect(page).toHaveURL(/\/workspace$/);
  await expect(page.getByRole("heading", { level: 1, name: "Cases" })).toBeVisible();
}

export async function loginWorkspace(page: Page, credentials: WorkspaceCredentials) {
  await page.goto("/auth/login");

  await page.getByLabel("Email").fill(credentials.email);
  await page.getByLabel("Organization slug").fill(credentials.organizationSlug);
  await page.getByLabel("Password").fill(credentials.password);

  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(/\/workspace$/);
  await expect(page.getByRole("heading", { level: 1, name: "Cases" })).toBeVisible();
}
