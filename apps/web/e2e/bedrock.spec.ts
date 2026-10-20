import { expect, test } from "@playwright/test";

// This test supplies a browser-only fixture response. It does not invoke AWS or
// store manufactured advice in the application's database.
test("validated advisory display, fact navigation and review feedback", async ({
  page,
}, testInfo) => {
  await page.goto("/");
  await page.request.post("/test/fixture-session");
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Cloud financial overview" }),
  ).toBeVisible();
  const records = (await (await page.request.get("/v1/recommendations")).json())
    .items;
  let rec = records.find(
    (item: { provider: string; category: string }) =>
      item.provider === "aws" && item.category === "compute",
  );
  await page.request.post(`/v1/recommendations/${rec.id}/analyze`, {
    data: { idempotency_key: `ui-advice-assess-${Date.now()}` },
  });
  rec = await (await page.request.get(`/v1/recommendations/${rec.id}`)).json();
  const state = await (await page.request.get("/v1/ai/status")).json();
  const draft = {
    generation_id: "browser-fixture-draft",
    generated_at: new Date().toISOString(),
    model_id: "global.anthropic.claude-opus-5-5",
    source_region: "ap-south-1",
    destination_regions: ["us-east-1"],
    prompt_version: "finops-advisor-v1",
    guardrail_version: "1",
    source_version: rec.version,
    evidence_hash: "fixture-hash",
    stale: false,
    cache_hit: false,
    validation: "Browser fixture: human review remains required.",
    latency_ms: 1200,
    usage: { inputTokens: 120, outputTokens: 250 },
    source_guide:
      "https://docs.aws.amazon.com/cost-management/latest/userguide/cost-optimization-hub.html",
    facts: [
      { id: "E5", field: "memory_peak_percent", value: null },
      { id: "E12", field: "policy_outcome", value: "NEEDS_EVIDENCE" },
    ],
    content: {
      summary:
        "Memory telemetry is incomplete, so gather evidence before considering a change.",
      summary_evidence_ids: ["E5", "E12"],
      priority: "gather_evidence",
      observations: [
        {
          statement: "Peak memory evidence is not available.",
          evidence_ids: ["E5"],
        },
      ],
      actions: [
        {
          id: "collect_telemetry",
          title: "Complete peak utilization evidence",
          guidance: "Collect representative peak telemetry.",
          prerequisite: "Missing metrics remain unknown.",
          evidence_ids: ["E5"],
        },
      ],
      open_questions: [
        "Can the owner provide representative peak memory telemetry?",
      ],
    },
  };
  let generated = false,
    feedback = "";
  await page.route("**/v1/ai/status", (route) =>
    route.fulfill({ json: { ...state, status: "READY_UNVERIFIED" } }),
  );
  await page.route(`**/v1/recommendations/${rec.id}`, (route) =>
    route.fulfill({ json: { ...rec, advisory: generated ? draft : null } }),
  );
  await page.route(`**/v1/recommendations/${rec.id}/advise`, (route) => {
    generated = true;
    return route.fulfill({ status: 202, json: { id: "browser-fixture-job" } });
  });
  await page.route("**/v1/jobs/browser-fixture-job", (route) =>
    route.fulfill({ json: { status: "SUCCEEDED" } }),
  );
  await page.route(
    `**/v1/recommendations/${rec.id}/advice/feedback`,
    (route) => {
      feedback = route.request().postDataJSON().verdict;
      return route.fulfill({ json: { ok: true } });
    },
  );
  await page.reload();
  await page.getByRole("button", { name: rec.title, exact: true }).click();
  await page
    .getByRole("button", { name: "Bedrock guidance", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Generate Bedrock guidance", exact: true })
    .click();
  await expect(
    page.getByText("AI-generated draft", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText(draft.content.summary, { exact: false }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Complete peak utilization evidence" }),
  ).toBeVisible();
  await page.screenshot({
    path: `../../artifacts/bedrock-draft-fixture-${testInfo.project.name}.png`,
  });
  await page.getByRole("link", { name: "E5", exact: true }).first().click();
  await expect(page.locator(".ai-facts")).toHaveAttribute("open", "");
  await expect(page.locator("#fact-E5")).toContainText("Unknown");
  await page.getByRole("button", { name: "Helpful", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Feedback recorded");
  expect(feedback).toBe("helpful");
});

test("client administrator explicitly approves global processing without invoking a model", async ({
  page,
}, testInfo) => {
  const inferenceRequests: string[] = [];
  page.on("request", (request) => {
    if (request.url().endsWith("/advise"))
      inferenceRequests.push(request.url());
  });
  await page.goto("/");
  await page
    .getByRole("button", { name: "Create a workspace", exact: true })
    .click();
  await page.getByLabel("Your name").fill("AI Policy Admin");
  await page
    .getByLabel("Organization", { exact: true })
    .fill("AI Policy Test Client");
  await page
    .getByLabel("Email address")
    .fill(`ai-policy-${testInfo.project.name}-${Date.now()}@example.test`);
  await page
    .getByLabel("Password", { exact: true })
    .fill("local-ai-policy-test-password");
  await page.getByRole("button", { name: /^Create workspace$/ }).click();
  await page.getByRole("button", { name: /^Settings$/ }).click();
  const controls = page.getByRole("region", { name: "Bedrock AI governance" });
  await expect(
    controls.getByText("global.anthropic.claude-opus-5-5", { exact: true }),
  ).toBeVisible();
  await expect(controls.getByLabel("Client processing policy")).toHaveValue(
    "india_only",
  );
  await expect(
    controls.getByLabel(/Enable Bedrock guidance/),
  ).not.toBeChecked();
  await controls.getByLabel(/Enable Bedrock guidance/).check();
  await expect(controls.getByLabel(/Enable Bedrock guidance/)).toBeChecked();
  await controls.getByLabel(/I am authorized by this client/).check();
  await expect(controls.getByLabel(/Enable Bedrock guidance/)).toBeChecked();
  await controls.getByRole("button", { name: "Save client AI policy" }).click();
  await expect(controls.getByRole("alert")).toContainText("India-only");
  await controls
    .getByLabel("Client processing policy")
    .selectOption("global_approved");
  await expect(
    controls.getByLabel(/I am authorized by this client/),
  ).not.toBeChecked();
  await controls.getByLabel(/I am authorized by this client/).check();
  await controls.getByRole("button", { name: "Save client AI policy" }).click();
  await expect(controls.getByRole("status")).toContainText(
    "No model was invoked",
  );
  await expect(
    controls.getByText(/Bedrock is integrated but disabled/),
  ).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: /^Settings$/ }).click();
  await expect(controls.getByLabel("Client processing policy")).toHaveValue(
    "global_approved",
  );
  await expect(
    controls.getByLabel(/I am authorized by this client/),
  ).toBeChecked();
  expect(
    await page.evaluate(
      () =>
        document.documentElement.scrollWidth <=
        document.documentElement.clientWidth + 1,
    ),
  ).toBeTruthy();
  expect(inferenceRequests).toEqual([]);
  await page.screenshot({
    path: `../../artifacts/bedrock-policy-${testInfo.project.name}.png`,
    fullPage: true,
  });
});
