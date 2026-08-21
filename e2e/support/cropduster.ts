import path from "node:path";
import { fileURLToPath } from "node:url";

import {
  expect,
  test,
  type FrameLocator,
  type Locator,
  type Page,
} from "@playwright/test";

export const REPO_DIR = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
  "..",
);

export const IMG_JPG = path.join(REPO_DIR, "tests", "data", "img.jpg");
export const IMG2_JPG = path.join(REPO_DIR, "tests", "data", "img2.jpg");

/** Matches `class="... disabled ..."` without matching e.g. `not-disabled`. */
const DISABLED = /(?:^|\s)disabled(?:\s|$)/;

/** The modal's host element, portaled to the opener's `document.body`. */
export const MODAL_HOST = "cropduster-dialog";

/** The same host, only while the modal is open. */
export const OPEN_MODAL_HOST = `${MODAL_HOST}[data-state="open"]`;

/** The full-page dialog's mount point, on `cropduster/upload.html`. */
export const PAGE_HOST = "#cropduster-app";

/** A page or frame containing widget markup. */
type Scope = Page | FrameLocator;

export type DialogMode = "modal" | "window";

/**
 * Return the dialog mode configured for the current Playwright project.
 *
 * The `fullpage` project points at a second demo server started with
 * `CROPDUSTER_DIALOG_MODE=window`; everywhere else the setting is `auto`, and a
 * desktop viewport resolves that to the modal.
 */
export function dialogMode(): DialogMode {
  return test.info().project.name === "fullpage" ? "window" : "modal";
}

/**
 * An open dialog and the document containing it.
 *
 * Both presentations use the same selector IDs under `root`. Playwright
 * traverses the open shadow root automatically.
 */
export interface Dialog {
  /** The document it is running in: a popup, or the page that opened it. */
  page: Page;
  /** Its shadow host. */
  root: Locator;
  /** Resolves once the crop has been returned and the dialog is gone. */
  waitForClose(): Promise<void>;
}

/**
 * The 4.x widget: `#<prefix>-group.cropduster-form` wrapping the hidden
 * formset, the upload anchor and the thumbnail container.
 */
export function widget(scope: Scope, prefix: string): Locator {
  return scope.locator(`#${prefix}-group.cropduster-form`);
}

/** Click "Upload Image" and return the modal inserted into the page. */
export async function openModalDialog(
  page: Page,
  group: Locator,
): Promise<Dialog> {
  await group.locator("a.cropduster-customfield").click();

  const host = page.locator(MODAL_HOST);
  await expect(host).toHaveCount(1);
  await expect(host).toHaveAttribute("data-state", "open");
  await host.locator("#id_image").waitFor({ state: "attached" });

  return {
    page,
    root: host,
    waitForClose: async () => {
      await expect(page.locator(OPEN_MODAL_HOST)).toHaveCount(0, {
        timeout: 30_000,
      });
    },
  };
}

/** Click "Upload Image" and return the window the dialog opened in. */
export async function openWindowDialog(
  page: Page,
  group: Locator,
): Promise<Dialog> {
  const popupPromise = page.waitForEvent("popup");
  await group.locator("a.cropduster-customfield").click();
  const popup = await popupPromise;
  await popup.waitForLoadState("domcontentloaded");

  const host = popup.locator(PAGE_HOST);
  await host.locator("#id_image").waitFor({ state: "attached" });

  return {
    page: popup,
    root: host,
    waitForClose: async () => {
      await expect
        .poll(() => popup.isClosed(), {
          timeout: 30_000,
          message: "the dialog should close itself after the last crop",
        })
        .toBe(true);
    },
  };
}

/** Click "Upload Image" and return whichever dialog the widget opened. */
export async function openDialog(page: Page, group: Locator): Promise<Dialog> {
  return dialogMode() === "window"
    ? openWindowDialog(page, group)
    : openModalDialog(page, group);
}

/**
 * Wait until the dialog is ready to crop.
 *
 * Not `#cropbox`: that `<img>` is mounted with a blank placeholder while the
 * upload is in progress, so waiting for it can finish before the crop step is
 * ready. Save is omitted until every configured size has a crop box.
 */
export async function waitForCropStep(dialog: Dialog) {
  await expect(dialog.root.locator("#image-container")).toBeVisible();
}

/**
 * Upload a file, populate every crop, save once, and wait for the dialog to close.
 *
 * When supplied, `expectedSteps` checks the number of parent sizes declared
 * by the field.
 */
export async function uploadAndCropAll(
  dialog: Dialog,
  file: string,
  expectedSteps?: number,
) {
  const { root } = dialog;
  await root.locator("#id_image").setInputFiles(file);
  await waitForCropStep(dialog);

  const stepCount = root.locator("#thumb-total-count");
  if (expectedSteps !== undefined) {
    await expect(stepCount).toHaveText(String(expectedSteps));
  }
  const total = Number(await stepCount.innerText());
  expect(total).toBeGreaterThan(0);

  const previews = root.locator(".crop-preview");
  for (let i = 1; i < total; i += 1) {
    await previews.nth(i).click();
  }

  const saveButton = root.locator("#crop-button");
  await expect(saveButton).toHaveValue("Save");
  await expect(saveButton).not.toHaveClass(DISABLED);
  await saveButton.click();

  await dialog.waitForClose();
}

/**
 * Locator for the `<option>`s `CropDuster.setThumbnails` writes into the
 * formset's thumbs select (and that the server re-renders after a save).
 */
export function selectedThumbOptions(scope: Scope, prefix: string): Locator {
  return scope.locator(`#id_${prefix}-0-thumbs option[selected]`);
}

/** The preview images rendered by `CropDuster.createThumbnails`. */
export function previewImages(group: Locator): Locator {
  return group.locator(".cropduster-images img.cropduster-image-thumb");
}

export async function saveAndContinue(page: Page) {
  await page.locator("input[name=_continue]").click();
  await expect(page.locator("ul.messagelist li.success")).toBeVisible();
}
