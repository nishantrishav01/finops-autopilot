import { defineConfig, devices } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  outputDir: "../../artifacts/playwright",
  fullyParallel: false,
  workers: 1,
  timeout: 45000,
  use: {
    baseURL: "http://127.0.0.1:8010",
    channel: "chrome",
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "desktop",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1440, height: 1050 },
      },
    },
    {
      name: "mobile",
      use: { ...devices["iPhone 13"], defaultBrowserType: "chromium" },
    },
  ],
  webServer: {
    command:
      '"../../.venv/Scripts/python.exe" -m uvicorn tests.browser_server:app --app-dir ../.. --host 127.0.0.1 --port 8010',
    url: "http://127.0.0.1:8010/health",
    reuseExistingServer: false,
    env: {
      FINOPS_DB: "../../.cache/browser-tests.db",
      FINOPS_VAULT_DIR: "../../.cache/browser-vault",
      FINOPS_ENABLE_LIVE: "false",
      FINOPS_BEDROCK_ENABLED: "false",
      FINOPS_BEDROCK_REGION: "ap-south-1",
      FINOPS_BEDROCK_MODEL_ID: "global.anthropic.claude-opus-5-5",
      FINOPS_BEDROCK_ALLOW_GLOBAL: "true",
    },
  },
});
