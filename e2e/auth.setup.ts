import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test as setup } from "@playwright/test";

const E2E_DIR = path.dirname(fileURLToPath(import.meta.url));
const STORAGE_STATE = path.join(E2E_DIR, ".auth", "admin.json");

setup("authenticate as the demo superuser", async ({ page }) => {
  await page.goto("/admin/login/?next=/admin/");
  await page.locator("#id_username").fill("admin");
  await page.locator("#id_password").fill("admin");
  await page.locator("input[type=submit]").click();

  await expect(page.locator("#user-tools")).toContainText("admin");

  await page.context().storageState({ path: STORAGE_STATE });
});
