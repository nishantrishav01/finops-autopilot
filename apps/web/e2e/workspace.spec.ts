import { test, expect } from "@playwright/test";

test("sample dashboard, provider filtering and accessible navigation", async ({
  page,
}, testInfo) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await page.request.post("/test/fixture-session");
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Cloud financial overview" }),
  ).toBeVisible();
  await expect(
    page.getByText("Total cloud spend", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("img", { name: /Daily stacked spend chart/ }),
  ).toBeVisible();
  await expect(
    page.locator(".kpi-card").nth(3).locator(".kpi-value"),
  ).toHaveText("03");
  const layout = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    inner: innerWidth,
    visual: visualViewport?.width,
    content: document.documentElement.scrollWidth,
    overflow: [
      ...document.querySelectorAll(
        "main,.main-shell,.kpi-grid,.kpi-card,.chart-grid,.card,.table-scroll,.bottom-grid,.page-footer,.filterbar",
      ),
    ]
      .map((n) => ({
        name: n.className,
        left: n.getBoundingClientRect().left,
        right: n.getBoundingClientRect().right,
        scroll: n.scrollWidth,
      }))
      .filter((n) => n.right > document.documentElement.clientWidth + 1),
  }));
  if (layout.content > layout.viewport + 1)
    console.log("Layout overflow:", JSON.stringify(layout));
  expect(layout.content).toBeLessThanOrEqual(layout.viewport + 1);
  await page.screenshot({
    path: `../../artifacts/dashboard-${testInfo.project.name}.png`,
    fullPage: true,
  });
  await page.getByLabel("Cloud provider", { exact: true }).selectOption("gcp");
  await expect(
    page.locator(".kpi-card").nth(3).locator(".kpi-value"),
  ).toHaveText("01");
  await expect(page.locator("tbody tr")).toHaveCount(2);
  await page.getByLabel("Cloud provider", { exact: true }).selectOption("all");
  await page.getByLabel("Date range").selectOption("7");
  await expect(page.getByText("vs. previous 7 days")).toBeVisible();
  await page.getByRole("button", { name: /^Cloud accounts$/ }).click();
  await expect(
    page.getByRole("heading", { name: "Cloud accounts", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".account-card")).toHaveCount(3);
  await page
    .getByRole("button", { name: /Connection details/ })
    .first()
    .click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByLabel("Close dialog").click();
  expect(errors).toEqual([]);
});

test("evidence assessment, review blocking and decision persistence", async ({
  page,
}) => {
  await page.goto("/");
  await page.request.post("/test/fixture-session");
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Cloud financial overview" }),
  ).toBeVisible();
  await page.request.post("/test/refresh-fixture", {
    data: { idempotency_key: `browser-reset-${Date.now()}` },
  });
  await page.reload();
  await page
    .getByRole("button", {
      name: "Rightsize underutilized EC2 instances",
      exact: true,
    })
    .click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(
    page.getByText("Missing evidence", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Assess evidence", exact: true })
    .click();
  await expect(
    page.getByText("Peak memory telemetry is missing.", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText(/Rule-based routing/)).toBeVisible();
  await page
    .getByRole("button", { name: "Bedrock guidance", exact: true })
    .click();
  await expect(
    page.getByRole("button", {
      name: "Generate Bedrock guidance",
      exact: true,
    }),
  ).toBeDisabled();
  await expect(
    page.getByText(/Bedrock is integrated but disabled/),
  ).toBeVisible();
  await page.getByRole("button", { name: "Review plan", exact: true }).click();
  await expect(
    page.getByRole("option", { name: /Approve plan/ }),
  ).toHaveAttribute("disabled", "");
  await page
    .getByLabel("Justification")
    .fill("Waiting for workload owner to provide peak memory evidence.");
  await page
    .getByRole("button", { name: "Record decision", exact: true })
    .click();
  await expect(
    page.getByText("Reviewer’s justification", { exact: true }),
  ).toBeVisible();
  await page.getByLabel("Close dialog").click();
  await page.getByRole("button", { name: /^Audit log$/ }).click();
  await expect(
    page.getByText("deferred", { exact: true }).first(),
  ).toBeVisible();
});

test("isolated client workspace and cloud import onboarding", async ({
  page,
}, testInfo) => {
  await page.goto("/");
  await page
    .getByRole("button", { name: "Create a workspace", exact: true })
    .click();
  await page.getByLabel("Your name").fill("Browser Test Admin");
  await page
    .getByLabel("Organization", { exact: true })
    .fill("Browser Test Client");
  await page
    .getByLabel("Email address")
    .fill(`browser-${testInfo.project.name}-${Date.now()}@example.test`);
  await page
    .getByLabel("Password", { exact: true })
    .fill("local-e2e-test-password-123");
  await page.getByRole("button", { name: /^Create workspace$/ }).click();
  await expect(
    page.getByRole("heading", { name: "Cloud financial overview" }),
  ).toBeVisible();
  await expect(
    page.locator(".kpi-card").nth(3).locator(".kpi-value"),
  ).toHaveText("00");
  await page
    .getByRole("button", { name: "Connect account", exact: true })
    .first()
    .click();
  await page
    .getByRole("button", { name: /Microsoft Azure Subscription/ })
    .click();
  await page.getByLabel(/Import client data/).check();
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await page.getByLabel("Connection name").fill("Client Azure import");
  await page
    .getByLabel("Azure subscription ID")
    .fill("11111111-1111-4111-8111-111111111111");
  await page.getByRole("button", { name: "Review setup", exact: true }).click();
  await page
    .getByRole("button", { name: "Register connection", exact: true })
    .click();
  await expect(
    page.getByRole("dialog", { name: "Connection details" }),
  ).toBeVisible();
  const day = new Date(Date.now() - 2 * 86400000).toISOString().slice(0, 10);
  await page.locator("input[type=file]").setInputFiles({
    name: "billing.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(
      `date,service,amount,currency\n${day},Virtual Machines,125.50,USD\n`,
    ),
  });
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(
    page.locator(".kpi-card").first().locator(".kpi-value"),
  ).toHaveText("$125.50");
  await page.reload();
  await expect(
    page.locator(".kpi-card").first().locator(".kpi-value"),
  ).toHaveText("$125.50");
  await page.getByRole("button", { name: /^Reports$/ }).click();
  await page
    .getByRole("button", { name: "Create CSV report", exact: true })
    .click();
  await expect(
    page.getByRole("link", { name: "Download", exact: true }),
  ).toBeVisible();
});
