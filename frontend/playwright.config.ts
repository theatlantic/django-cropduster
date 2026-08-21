import path from "node:path";
import { fileURLToPath } from "node:url";

import { defineConfig, devices } from "@playwright/test";

const FRONTEND_DIR = path.dirname(fileURLToPath(import.meta.url));
const REPO_DIR = path.resolve(FRONTEND_DIR, "..");
const E2E_DIR = path.join(REPO_DIR, "e2e");

const HOST = process.env.CROPDUSTER_E2E_HOST ?? "127.0.0.1";
const PORT = process.env.CROPDUSTER_E2E_PORT ?? "8017";
const BASE_URL = `http://${HOST}:${PORT}`;

/**
 * Run a second demo server with `CROPDUSTER_DIALOG_MODE=window`.
 *
 * Django renders the dialog mode into the widget's `data-config`, so the popup
 * tests need a server process with the setting already applied. Both servers
 * use the same database. Cookies ignore the port, so the setup session works
 * for both and the fixtures are seeded once.
 */
const WINDOW_PORT = process.env.CROPDUSTER_E2E_WINDOW_PORT ?? "8018";
const WINDOW_BASE_URL = `http://${HOST}:${WINDOW_PORT}`;

const STORAGE_STATE = path.join(E2E_DIR, ".auth", "admin.json");

const manage = (args: string) =>
  `uv run --project ../demo python ../demo/src/manage.py ${args}`;

export default defineConfig({
  testDir: E2E_DIR,
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  timeout: 90_000,
  expect: { timeout: 20_000 },
  reporter: process.env.CI
    ? [["github"], ["html", { open: "never" }]]
    : [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: BASE_URL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off",
  },
  projects: [
    {
      name: "setup",
      testMatch: /.*\.setup\.ts$/,
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "chromium",
      testMatch: /.*\.spec\.ts$/,
      dependencies: ["setup"],
      use: {
        ...devices["Desktop Chrome"],
        storageState: STORAGE_STATE,
      },
    },
    {
      // Rerun formset-result scenarios against the popup. Exclude tests for
      // modal-only behavior, its JSON requests, and the iframe fallback.
      name: "fullpage",
      testMatch: /(widget|nested)\.spec\.ts$/,
      dependencies: ["setup"],
      use: {
        ...devices["Desktop Chrome"],
        storageState: STORAGE_STATE,
        baseURL: WINDOW_BASE_URL,
      },
    },
  ],
  webServer: [
    {
      command: [
        manage("migrate --noinput"),
        manage("seed_e2e"),
        manage(`runserver ${HOST}:${PORT} --noreload`),
      ].join(" && "),
      cwd: FRONTEND_DIR,
      url: `${BASE_URL}/admin/login/`,
      reuseExistingServer: !process.env.CI,
      timeout: 180_000,
      stdout: "ignore",
      stderr: "pipe",
    },
    {
      // The first server migrates and seeds the shared database. This server
      // differs only in the setting used to render widgets.
      command: manage(`runserver ${HOST}:${WINDOW_PORT} --noreload`),
      cwd: FRONTEND_DIR,
      url: `${WINDOW_BASE_URL}/admin/login/`,
      env: { CROPDUSTER_DIALOG_MODE: "window" },
      reuseExistingServer: !process.env.CI,
      timeout: 180_000,
      stdout: "ignore",
      stderr: "pipe",
    },
  ],
});

export { BASE_URL, E2E_DIR, REPO_DIR, STORAGE_STATE, WINDOW_BASE_URL };
