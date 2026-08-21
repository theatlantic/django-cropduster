import { expect, test } from "@playwright/test";

import {
  IMG_JPG,
  MODAL_HOST,
  OPEN_MODAL_HOST,
  openWindowDialog,
  previewImages,
  selectedThumbOptions,
  uploadAndCropAll,
  widget,
} from "./support/cropduster";

/**
 * Run the admin inside a downstream editor's 830x550 non-scrolling iframe.
 *
 * The demo retains `CROPDUSTER_DIALOG_MODE="auto"`. At this viewport size the
 * widget must open a popup because the modal cannot fit. The popup returns its
 * result through `window.opener.CropDuster.complete()` in the iframe; it must
 * not use `postMessage`, which a downstream script consumes with a one-time
 * listener.
 */

const FRAME_NAME = "article-frame";

test("opens a window rather than a modal, and the crop lands in the frame", async ({
  page,
}) => {
  await page.goto("/tiny-iframe/");

  const frame = page.frame({ name: FRAME_NAME });
  expect(frame, "the demo page should embed the change form").not.toBeNull();
  const [width, height] = await frame!.evaluate(() => [
    window.innerWidth,
    window.innerHeight,
  ]);
  expect(width).toBeLessThan(900);
  expect(height).toBeLessThan(600);

  const embedded = page.frameLocator(`#${FRAME_NAME}`);
  await embedded.locator("#id_title").fill(`Iframe article ${Date.now()}`);

  const group = widget(embedded, "lead_image");
  await expect(previewImages(group)).toHaveCount(0);

  // `openWindowDialog` fails if the widget does not open a popup.
  const dialog = await openWindowDialog(page, group);
  expect(dialog.page).not.toBe(page);
  expect(
    await frame!.evaluate(
      (selector) => document.querySelectorAll(selector).length,
      OPEN_MODAL_HOST,
    ),
    "no modal should have been put up in a viewport this size",
  ).toBe(0);

  await uploadAndCropAll(dialog, IMG_JPG, 2);

  // The popup writes the result to the iframe that opened it and updates the
  // widget clicked inside that iframe.
  await expect(previewImages(group)).toHaveCount(1);
  await expect(embedded.locator("#id_lead_image")).not.toHaveValue("");
  await expect(selectedThumbOptions(embedded, "lead_image")).not.toHaveCount(0);

  // The outer page does not receive a modal host.
  await expect(page.locator(MODAL_HOST)).toHaveCount(0);
});
