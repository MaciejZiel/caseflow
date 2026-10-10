import { expect, test } from "@playwright/test";

import { createWorkspaceCredentials, loginWorkspace, registerWorkspace } from "./helpers";

test.describe("CaseFlow workspace", () => {
  test("registers a workspace and signs back in", async ({ page }) => {
    const credentials = createWorkspaceCredentials("E2E Auth");

    await registerWorkspace(page, credentials);

    await page.getByRole("button", { name: "Sign out" }).click();
    await expect(page).toHaveURL(/\/auth\/login$/);

    await loginWorkspace(page, credentials);
  });

  test("creates a case, uploads a document, and gets a grounded assistant answer", async ({
    page,
  }) => {
    const credentials = createWorkspaceCredentials("E2E Assistant");
    const caseTitle = `Playwright claim ${Date.now()}`;
    const documentTitle = "Repair estimate";
    const question = "What is missing before this case can move forward?";

    await registerWorkspace(page, credentials);

    await page.getByLabel("Case title").fill(caseTitle);
    await page.getByLabel("External reference").fill(`PW-${Date.now()}`);
    await page.getByLabel("Priority").selectOption("high");
    await page
      .getByLabel("Intake note")
      .fill("Customer submitted a draft repair estimate and the team needs a review.");

    await page.getByRole("button", { name: "Create and open case" }).click();
    await expect(page).toHaveURL(/\/workspace\/cases\//);
    await expect(page.getByRole("heading", { name: caseTitle })).toBeVisible();

    await page.getByLabel("Title").fill(documentTitle);
    await page.getByLabel("Document type").selectOption("invoice");
    await page.getByLabel("File").setInputFiles({
      name: "repair-estimate.txt",
      mimeType: "text/plain",
      buffer: Buffer.from(
        [
          "Claim reference PLAYWRIGHT-1001",
          "Unsigned repair estimate for front bumper damage.",
          "Awaiting claimant approval.",
          "Missing insurer confirmation.",
        ].join("\n"),
      ),
    });
    await page.getByRole("button", { name: "Upload document" }).click();

    const documentRow = page.getByRole("row").filter({ hasText: documentTitle }).first();
    await expect(documentRow).toBeVisible();

    const assistantSection = page
      .locator("section")
      .filter({ has: page.getByRole("heading", { name: "Assistant", exact: true }) });

    await assistantSection.getByRole("button", { name: "New thread" }).click();
    await assistantSection.getByRole("button", { name: "Review Assistant" }).click();
    await assistantSection.getByLabel("Ask the assistant").fill(question);
    await assistantSection.getByRole("button", { name: "Ask", exact: true }).click();

    await expect(assistantSection.getByText(question, { exact: true })).toBeVisible();
    await expect(assistantSection.getByText("Sources", { exact: true })).toBeVisible();
    await expect(assistantSection.getByText(documentTitle, { exact: true })).toBeVisible();
    await expect(assistantSection.getByText(/Recommended next actions/i)).toBeVisible();
  });
});
