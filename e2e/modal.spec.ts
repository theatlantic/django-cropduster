import { expect, test, type Page } from "@playwright/test";

import {
  IMG_JPG,
  MODAL_HOST,
  OPEN_MODAL_HOST,
  openModalDialog,
  previewImages,
  saveAndContinue,
  selectedThumbOptions,
  uploadAndCropAll,
  waitForCropStep,
  widget,
} from "./support/cropduster";

/**
 * Modal-specific behavior.
 *
 * These tests verify that only one modal exists, page scrolling is locked,
 * focus remains inside the modal, and Escape or backdrop dismissal leaves the
 * formset unchanged. `widget.spec.ts` covers upload and crop behavior through
 * the same modal.
 *
 * This file is excluded from the `fullpage` Playwright project.
 */

const ADD_URL = "/admin/example/article/add/";

/** Return the computed overflow values for the document and body. */
function overflows(page: Page) {
  return page.evaluate(() => [
    getComputedStyle(document.documentElement).overflow,
    getComputedStyle(document.body).overflow,
  ]);
}

test("puts up exactly one host, and takes it down again", async ({ page }) => {
  await page.goto(ADD_URL);

  const host = page.locator(MODAL_HOST);
  await expect(page.locator(OPEN_MODAL_HOST)).toHaveCount(0);

  const dialog = await openModalDialog(page, widget(page, "lead_image"));
  await expect(host).toHaveCount(1);
  await expect(host).toHaveAttribute("data-state", "open");
  // The chooser is inside the host's shadow root. The compatibility Upload
  // control remains hidden.
  await expect(dialog.root.locator(".upload-file-control")).toBeVisible();
  await expect(dialog.root.locator("#upload-button")).toBeHidden();
  await expect(page.locator("body > .upload-file-control")).toHaveCount(0);

  await page.keyboard.press("Escape");
  await expect(page.locator(OPEN_MODAL_HOST)).toHaveCount(0);

  // Opening a dialog from another field still leaves exactly one modal.
  await openModalDialog(page, widget(page, "alt_image"));
  await expect(page.locator(OPEN_MODAL_HOST)).toHaveCount(1);
  await expect(host).toHaveCount(1);
});

test("locks the page's scrolling while it is up", async ({ page }) => {
  await page.goto(ADD_URL);

  const before = await overflows(page);
  expect(before).not.toContain("hidden");

  await openModalDialog(page, widget(page, "lead_image"));
  expect(await overflows(page)).toContain("hidden");

  await page.keyboard.press("Escape");
  await expect(page.locator(OPEN_MODAL_HOST)).toHaveCount(0);
  expect(await overflows(page)).toEqual(before);
});

/** Return the focused element's identifier from inside the shadow root. */
function focusedInDialog(page: Page) {
  return page.evaluate(() => {
    const host = document.querySelector("cropduster-dialog");
    const active = host?.shadowRoot?.activeElement;
    if (!active) {
      return null;
    }
    return active.id || active.className || active.tagName;
  });
}

/** Return the controls visited by successive Tab presses. */
async function tabStops(page: Page, presses: number) {
  const seen: (string | null)[] = [];
  for (let i = 0; i < presses; i += 1) {
    await page.keyboard.press("Tab");
    seen.push(await focusedInDialog(page));
  }
  return seen;
}

/** Press Tab up to `presses` times and report whether `id` receives focus. */
async function tabTo(page: Page, id: string, presses = 18) {
  for (let i = 0; i < presses; i += 1) {
    if ((await focusedInDialog(page)) === id) {
      return true;
    }
    await page.keyboard.press("Tab");
  }
  return (await focusedInDialog(page)) === id;
}

test("keeps the focus inside itself", async ({ page }) => {
  const HOST_TAG = MODAL_HOST.toUpperCase();
  await page.goto(ADD_URL);
  await page.locator("#id_title").focus();

  await openModalDialog(page, widget(page, "lead_image"));

  // From the page, focus inside an open shadow root is reported as the host.
  // This check does not depend on which dialog control is focused.
  const focusedTag = () =>
    page.evaluate(() => document.activeElement?.tagName ?? null);
  await expect.poll(focusedTag).toBe(HOST_TAG);

  // The panel is open through showModal(), so the browser itself keeps the
  // page behind it inert and its controls out of the tab order.
  expect(
    await page.evaluate(
      () =>
        document
          .querySelector("cropduster-dialog")
          ?.shadowRoot?.querySelector("dialog")
          ?.matches(":modal") ?? false,
    ),
  ).toBe(true);

  // This exceeds the number of dialog controls. Tab cycles through the
  // dialog's controls and the browser's own UI; while the browser's UI holds
  // focus the page reports BODY. No stop is ever a control of the inert
  // change form behind the modal.
  const stops: (string | null)[] = [];
  for (let i = 0; i < 25; i += 1) {
    await page.keyboard.press("Tab");
    stops.push(await focusedTag());
  }
  expect(stops.every((tag) => tag === HOST_TAG || tag === "BODY")).toBe(true);
  // Focus returns to the dialog after each pass through the browser's UI
  // rather than escaping into the page.
  expect(stops.lastIndexOf(HOST_TAG)).toBeGreaterThan(stops.indexOf("BODY"));
  expect(stops.filter((tag) => tag === HOST_TAG).length).toBeGreaterThan(
    stops.length / 2,
  );

  await page.keyboard.press("Shift+Tab");
  expect([HOST_TAG, "BODY"]).toContain(await focusedTag());
});

/**
 * Hidden edge handles retain their `tabindex` under a fixed aspect ratio. A
 * focus trap based only on document order can stop on one of those handles and
 * make the remaining controls, including the crop button, unreachable.
 */
test("reaches every control at the crop step, in both directions", async ({
  page,
}) => {
  await page.goto(ADD_URL);
  const dialog = await openModalDialog(page, widget(page, "lead_image"));

  await dialog.root.locator("#id_image").setInputFiles(IMG_JPG);
  await waitForCropStep(dialog);
  expect(await focusedInDialog(page)).toBe("step-header");

  const forwards = await tabStops(page, 18);
  // One of two sizes is populated, so Save is omitted and the footer's
  // primary action is the next pending size; the source chip is focusable.
  expect(forwards).toContain("next-crop-button");
  expect(forwards).toContain("source-chip");
  expect(forwards).not.toContain("crop-button");
  expect(
    forwards.some((stop) => stop?.includes("ReactCrop__crop-selection")),
  ).toBe(true);
  // Only enabled size arrows belong to the tab sequence. `lead_image` opens on
  // the first of two sizes, so the left arrow is disabled and skipped.
  expect(forwards).toContain("nav-right");
  expect(forwards).not.toContain("nav-left");
  // Each press visits another control until the sequence wraps. Repeating an
  // id immediately would show that focus had stopped moving.
  for (let i = 1; i < forwards.length; i += 1) {
    expect([i, forwards[i]]).not.toEqual([i, forwards[i - 1]]);
  }
  // Edge handles stay visible, and focusable, under a fixed aspect ratio.
  expect(forwards).toContain("ReactCrop__drag-handle ord-n");

  const backwards: (string | null)[] = [];
  for (let i = 0; i < 4; i += 1) {
    await page.keyboard.press("Shift+Tab");
    backwards.push(await focusedInDialog(page));
  }
  expect(backwards).toEqual(
    forwards.slice(-backwards.length - 1, -1).reverse(),
  );

  // Focus never reaches the inert page behind the modal: from the page, a
  // focused dialog control reads as the host, and the browser's own UI (a
  // possible stop between wrap-arounds) reads as BODY.
  expect([MODAL_HOST.toUpperCase(), "BODY"]).toContain(
    await page.evaluate(() => document.activeElement?.tagName ?? null),
  );

  // Populating the remaining size arms Save, which joins the cycle.
  await dialog.root.locator(".crop-preview").nth(1).click();
  await expect(dialog.root.locator("#crop-button:not(.disabled)")).toHaveValue(
    "Save",
  );
  expect(await tabTo(page, "crop-button", 16)).toBe(true);
});

/** Size navigation uses buttons, so Enter and Space activate focused arrows. */
test("moves between sizes from the keyboard", async ({ page }) => {
  await page.goto(ADD_URL);
  const dialog = await openModalDialog(page, widget(page, "lead_image"));

  await dialog.root.locator("#id_image").setInputFiles(IMG_JPG);
  await waitForCropStep(dialog);

  const index = dialog.root.locator("#current-thumb-index");
  await expect(dialog.root.locator("#thumb-total-count")).toHaveText("2");
  await expect(index).toHaveText("1");

  expect(await tabTo(page, "nav-right")).toBe(true);
  await page.keyboard.press("Enter");
  await expect(index).toHaveText("2");

  // The last size disables the right arrow and enables the left arrow.
  await expect(dialog.root.locator("#nav-right")).toBeDisabled();
  expect(await tabTo(page, "nav-left")).toBe(true);
  await page.keyboard.press(" ");
  await expect(index).toHaveText("1");
});

test("closes on Escape and on the backdrop, writing nothing", async ({
  page,
}) => {
  await page.goto(ADD_URL);
  const group = widget(page, "lead_image");
  const dataField = page.locator("#id_lead_image");

  await openModalDialog(page, group);
  await page.keyboard.press("Escape");
  await expect(page.locator(OPEN_MODAL_HOST)).toHaveCount(0);

  const dialog = await openModalDialog(page, group);
  // The backdrop covers the viewport, so the corner is outside the dialog.
  await page.mouse.click(5, 5);
  await dialog.waitForClose();

  await expect(dataField).toHaveValue("");
  await expect(page.locator("#id_lead_image-0-image")).toHaveValue("");
  await expect(selectedThumbOptions(page, "lead_image")).toHaveCount(0);
  await expect(previewImages(group)).toHaveCount(0);
});

test("leaves Escape to an open source menu, then takes it back", async ({
  page,
}) => {
  await page.goto(ADD_URL);
  await page.locator("#id_title").fill(`Modal menu ${Date.now()}`);

  const lead = widget(page, "lead_image");
  await uploadAndCropAll(await openModalDialog(page, lead), IMG_JPG, 2);
  await saveAndContinue(page);

  const dialog = await openModalDialog(page, widget(page, "lead_image"));
  await waitForCropStep(dialog);

  await dialog.root.locator("#source-chip").click();
  await expect(dialog.root.locator("#source-menu")).toBeVisible();

  // The menu owns the first Escape: its handler closes the menu, stops the
  // press before it reaches the shell, and prevents the browser from
  // treating it as a dialog cancel. The modal stays up.
  await page.keyboard.press("Escape");
  await expect(dialog.root.locator("#source-menu")).toHaveCount(0);
  await expect(page.locator(OPEN_MODAL_HOST)).toHaveCount(1);

  // With the menu gone, Escape closes the modal.
  await page.keyboard.press("Escape");
  await dialog.waitForClose();
  await expect(page.locator(OPEN_MODAL_HOST)).toHaveCount(0);
});

test("writes the crop into the formset of the widget it was opened from", async ({
  page,
}) => {
  const title = `Modal article ${Date.now()}`;
  await page.goto(ADD_URL);
  await page.locator("#id_title").fill(title);

  const lead = widget(page, "lead_image");
  const alt = widget(page, "alt_image");

  const dialog = await openModalDialog(page, lead);
  expect(dialog.page).toBe(page);
  // `lead_image` declares two croppable sizes: `main` (with an auto `thumb`)
  // and `no_height`.
  await uploadAndCropAll(dialog, IMG_JPG, 2);

  // Closing the modal restores page scrolling.
  await expect(page.locator(OPEN_MODAL_HOST)).toHaveCount(0);
  expect(await overflows(page)).not.toContain("hidden");

  await expect(previewImages(lead)).toHaveCount(1);
  await expect(selectedThumbOptions(page, "lead_image")).not.toHaveCount(0);
  await expect(page.locator("#id_lead_image")).not.toHaveValue("");
  await expect(page.locator("#id_lead_image-TOTAL_FORMS")).toHaveValue("1");

  // The other field on the form is untouched.
  await expect(previewImages(alt)).toHaveCount(0);
  await expect(page.locator("#id_alt_image")).toHaveValue("");

  await saveAndContinue(page);

  await expect(page).toHaveURL(/\/admin\/example\/article\/\d+\/change\//);
  await expect(previewImages(widget(page, "lead_image"))).toHaveCount(1);
  const options = selectedThumbOptions(page, "lead_image");
  await expect(options).not.toHaveCount(0);
  await expect(options.first()).toHaveAttribute("value", /^\d+$/);
});

test("reopens on a field that already has a crop", async ({ page }) => {
  await page.goto(ADD_URL);
  await page.locator("#id_title").fill(`Modal reopen ${Date.now()}`);

  const lead = widget(page, "lead_image");
  await uploadAndCropAll(await openModalDialog(page, lead), IMG_JPG, 2);
  await saveAndContinue(page);

  const saved = widget(page, "lead_image");
  const thumbsBefore = await selectedThumbOptions(
    page,
    "lead_image",
  ).evaluateAll((options) =>
    options.map((option) => (option as HTMLOptionElement).value),
  );
  expect(thumbsBefore.length).toBeGreaterThan(0);

  // Reopening the saved field starts at the crop step, not the upload form.
  const dialog = await openModalDialog(page, saved);
  await waitForCropStep(dialog);
  await expect(dialog.root.locator("#thumb-total-count")).toHaveText("2");
  await page.keyboard.press("Escape");
  await dialog.waitForClose();

  await expect(previewImages(saved)).toHaveCount(1);
  expect(
    await selectedThumbOptions(page, "lead_image").evaluateAll((options) =>
      options.map((option) => (option as HTMLOptionElement).value),
    ),
  ).toEqual(thumbsBefore);
});
