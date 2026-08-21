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
 * Add a django-nested-admin row, crop its image, and save it.
 *
 * The new row is cloned from the `__prefix__` template. This verifies that the
 * widget mounts after nested-admin rewrites the prefix and that its formset
 * values are saved on the new row.
 *
 * The test runs against both modal and popup presentations.
 */
test("uploads and crops in a row added by nested-admin", async ({ page }) => {
  await page.goto("/admin/example/gallery/add/");
  await page.locator("#id_title").fill(`Nested gallery ${Date.now()}`);
  await saveAndContinue(page);
  await expect(page).toHaveURL(/\/admin\/example\/gallery\/\d+\/change\//);

  const photos = page.locator("#photos-group");
  await expect(
    photos.locator(".djn-inline-form:not(.djn-empty-form)"),
  ).toHaveCount(0);

  await photos.getByRole("link", { name: "Add another Photo" }).click();

  const group = widget(page, "photos-0-image");
  await expect(group).toBeVisible();
  await expect(previewImages(group)).toHaveCount(0);
  await page.locator("#id_photos-0-caption").fill("Nested photo");

  const dialog = await openDialog(page, group);
  await uploadAndCropAll(dialog, IMG2_JPG);

  await expect(previewImages(group)).toHaveCount(1);
  await expect(selectedThumbOptions(page, "photos-0-image")).not.toHaveCount(0);
  await expect(page.locator("#id_photos-0-image")).not.toHaveValue("");

  await saveAndContinue(page);

  // After saving, the server rebuilds the widget for the row added by the
  // client.
  const savedGroup = widget(page, "photos-0-image");
  await expect(savedGroup).toBeVisible();
  await expect(page.locator("#id_photos-0-caption")).toHaveValue(
    "Nested photo",
  );
  await expect(previewImages(savedGroup)).toHaveCount(1);
  const options = selectedThumbOptions(page, "photos-0-image");
  await expect(options).not.toHaveCount(0);
  await expect(options.first()).toHaveAttribute("value", /^\d+$/);
});
