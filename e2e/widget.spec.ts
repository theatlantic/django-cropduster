import { expect, test } from "@playwright/test";

import {
  IMG2_JPG,
  openDialog,
  previewImages,
  saveAndContinue,
  selectedThumbOptions,
  uploadAndCropAll,
  widget,
} from "./support/cropduster";

/**
 * Upload and save a top-level Cropduster field on a normal admin form.
 *
 * The assertions check the resulting formset and database state, so the same
 * tests run against both modal and popup presentations. The `fullpage` project
 * uses a server configured with `CROPDUSTER_DIALOG_MODE=window`.
 */
test("uploads and crops a top-level field through the dialog", async ({
  page,
}) => {
  const title = `Baseline article ${Date.now()}`;

  await page.goto("/example/article/add/");
  await page.locator("#id_title").fill(title);

  const group = widget(page, "lead_image");
  await expect(group).toBeVisible();
  await expect(previewImages(group)).toHaveCount(0);

  const dialog = await openDialog(page, group);
  await uploadAndCropAll(dialog, IMG2_JPG, 4);

  // `CropDuster.complete` writes the formset back and renders the preview.
  await expect(previewImages(group)).toHaveCount(1);
  await expect(selectedThumbOptions(page, "lead_image")).not.toHaveCount(0);
  await expect(page.locator("#id_lead_image")).not.toHaveValue("");
  await expect(page.locator("#id_lead_image-TOTAL_FORMS")).toHaveValue("1");

  await saveAndContinue(page);

  // After saving, the server rebuilds the widget from the stored formset data.
  await expect(page).toHaveURL(/\/example\/article\/\d+\/change\//);
  const savedGroup = widget(page, "lead_image");
  await expect(previewImages(savedGroup)).toHaveCount(1);
  const options = selectedThumbOptions(page, "lead_image");
  await expect(options).not.toHaveCount(0);
  await expect(options.first()).toHaveAttribute("value", /^\d+$/);

  // After a reload, the change form still shows the preview and thumbnails.
  const url = page.url();
  await page.goto(url);
  await expect(previewImages(widget(page, "lead_image"))).toHaveCount(1);
  await expect(selectedThumbOptions(page, "lead_image")).not.toHaveCount(0);
  await expect(page.locator("#id_lead_image")).not.toHaveValue("");
});

test("leaves the second field on the same form untouched", async ({ page }) => {
  await page.goto("/example/article/add/");
  await page.locator("#id_title").fill(`Two fields ${Date.now()}`);

  const lead = widget(page, "lead_image");
  const alt = widget(page, "alt_image");
  await expect(lead).toBeVisible();
  await expect(alt).toBeVisible();

  const dialog = await openDialog(page, lead);
  await uploadAndCropAll(dialog, IMG2_JPG, 4);

  await expect(previewImages(lead)).toHaveCount(1);
  await expect(previewImages(alt)).toHaveCount(0);
  await expect(page.locator("#id_alt_image")).toHaveValue("");
});
