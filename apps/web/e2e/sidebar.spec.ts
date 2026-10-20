import { expect, test } from "@playwright/test";

test("short screens can scroll the sidebar and reach its lower navigation", async ({
  page,
}, info) => {
  await page.setViewportSize(
    info.project.name === "mobile"
      ? { width: 390, height: 430 }
      : { width: 1366, height: 600 },
  );
  const registered = await page.request.post("/v1/auth/signup", {
    data: {
      name: "Navigation Test",
      organization: "Navigation workspace",
      email: `navigation-${info.project.name}-${Date.now()}@example.test`,
      password: "navigation-test-password-123",
    },
  });
  expect(registered.status()).toBe(201);
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Cloud financial overview" }),
  ).toBeVisible();
  const sidebar = page.locator(".sidebar");
  await expect
    .poll(() =>
      sidebar.evaluate((node) => node.scrollHeight > node.clientHeight),
    )
    .toBe(true);
  await sidebar.hover();
  await page.mouse.wheel(0, 1800);
  await expect
    .poll(() => sidebar.evaluate((node) => node.scrollTop))
    .toBeGreaterThan(0);
  await expect(
    sidebar.getByRole("button", { name: "Settings", exact: true }),
  ).toBeInViewport();
  await expect(
    sidebar.getByRole("button", { name: "Help and documentation" }),
  ).toBeInViewport();
  await sidebar.getByRole("button", { name: "Settings", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Workspace details" }),
  ).toBeVisible();
  await sidebar.hover();
  await page.mouse.wheel(0, -1800);
  await expect.poll(() => sidebar.evaluate((node) => node.scrollTop)).toBe(0);
  await expect(
    sidebar.getByRole("button", { name: "Overview", exact: true }),
  ).toBeInViewport();
});
