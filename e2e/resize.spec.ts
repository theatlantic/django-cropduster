/** Resizing the crop box by dragging a handle. */

import { expect, test } from "@playwright/test";

import { openDialog, waitForCropStep, widget } from "./support/cropduster";

/** A generated JPEG large enough to leave real room around the minimums. */
async function bigImage(page: import("@playwright/test").Page) {
  const base64 = await page.evaluate(async () => {
    const canvas = new OffscreenCanvas(2400, 1600);
    const ctx = canvas.getContext("2d")!;
    const gradient = ctx.createLinearGradient(0, 0, 2400, 1600);
    gradient.addColorStop(0, "#1e78c8");
    gradient.addColorStop(1, "#e8f0c0");
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, 2400, 1600);
    const blob = await canvas.convertToBlob({
      type: "image/jpeg",
      quality: 0.85,
    });
    const bytes = new Uint8Array(await blob.arrayBuffer());
    let out = "";
    for (const byte of bytes) {
      out += String.fromCharCode(byte);
    }
    return btoa(out);
  });
  return {
    name: "resize-probe.jpg",
    mimeType: "image/jpeg",
    buffer: Buffer.from(base64, "base64"),
  };
}

test("the crop box can be resized by its corner handles", async ({ page }) => {
  await page.goto("/admin/example/article/add/");
  await page.locator("#id_title").fill(`Resize probe ${Date.now()}`);

  const dialog = await openDialog(page, widget(page, "lead_image"));
  await dialog.root.locator("#id_image").setInputFiles(await bigImage(page));
  await waitForCropStep(dialog);

  // The handles must be grabbable: the library sizes them with
  // `--rc-drag-handle-size` (12px), which only reaches the shadow tree
  // through the `:root` -> `:host` rewrite.
  const seHandle = dialog.root.locator(".ReactCrop__drag-handle.ord-se");
  const handleBox = await seHandle.boundingBox();
  expect(handleBox, "the se handle renders").not.toBeNull();
  expect(handleBox!.width).toBeGreaterThanOrEqual(8);
  expect(handleBox!.height).toBeGreaterThanOrEqual(8);

  const selection = dialog.root.locator(".ReactCrop__crop-selection");
  const before = (await selection.boundingBox())!;

  await page.mouse.move(
    handleBox!.x + handleBox!.width / 2,
    handleBox!.y + handleBox!.height / 2,
  );
  await page.mouse.down();
  await page.mouse.move(
    handleBox!.x + handleBox!.width / 2 - 150,
    handleBox!.y + handleBox!.height / 2 - 100,
    { steps: 10 },
  );
  await page.mouse.up();

  const after = (await selection.boundingBox())!;
  expect(
    before.width - after.width,
    "dragging the corner inward shrinks the selection",
  ).toBeGreaterThan(50);

  // `main` is 600x480: the fixed ratio must hold through the drag.
  expect(after.width / after.height).toBeCloseTo(600 / 480, 1);

  // Edge handles are visible under a fixed aspect, with Jcrop semantics:
  // dragging the east edge keeps the west edge fixed, follows the pointer,
  // and holds the ratio.
  const eHandle = dialog.root.locator(".ReactCrop__drag-handle.ord-e");
  const eBox = (await eHandle.boundingBox())!;
  expect(eBox, "the east handle renders").not.toBeNull();
  await page.mouse.move(eBox.x + eBox.width / 2, eBox.y + eBox.height / 2);
  await page.mouse.down();
  await page.mouse.move(
    eBox.x + eBox.width / 2 + 80,
    eBox.y + eBox.height / 2,
    { steps: 8 },
  );
  await page.mouse.up();

  const widened = (await selection.boundingBox())!;
  expect(
    widened.width - after.width,
    "dragging the east edge outward grows the selection",
  ).toBeGreaterThan(60);
  expect(widened.width / widened.height).toBeCloseTo(600 / 480, 1);
  expect(Math.abs(widened.x - after.x), "the west edge stays put").toBeLessThan(
    2,
  );

  // And the north edge grows upward or slides while the south edge holds.
  const nHandle = dialog.root.locator(".ReactCrop__drag-handle.ord-n");
  const nBox = (await nHandle.boundingBox())!;
  await page.mouse.move(nBox.x + nBox.width / 2, nBox.y + nBox.height / 2);
  await page.mouse.down();
  await page.mouse.move(
    nBox.x + nBox.width / 2,
    nBox.y + nBox.height / 2 + 60,
    { steps: 8 },
  );
  await page.mouse.up();

  const shortened = (await selection.boundingBox())!;
  expect(
    widened.height - shortened.height,
    "dragging the north edge inward shrinks the selection",
  ).toBeGreaterThan(40);
  expect(shortened.width / shortened.height).toBeCloseTo(600 / 480, 1);
  expect(
    Math.abs(shortened.y + shortened.height - (widened.y + widened.height)),
    "the south edge stays put",
  ).toBeLessThan(2);

  // `lead_image` has a second size; the footer's Next action visits it,
  // which seeds its crop and arms Save.
  await dialog.root.locator("#next-crop-button").click();

  // The resized box round-trips: submitting the step must not error.
  await dialog.root.locator("#crop-button:not(.disabled)").click();
  await waitForCropStep(dialog);
});
