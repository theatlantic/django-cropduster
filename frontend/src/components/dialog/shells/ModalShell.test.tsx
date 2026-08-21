/**
 * Cover modal lifecycle, focus handling, completion, and a formset row renamed
 * while the dialog is open.
 */

import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { UPDATE_EVENT } from "../../../compat/events";
import { installGlobalApi } from "../../../compat/globalApi";
import { LOADING_CROPS } from "../../../constants/dialogLabels";
import { defineWidgetElement } from "../../../dom/CropDusterWidgetElement";
import { registry } from "../../../dom/registry";
import { dialogConfig } from "../../../testing/dialogFixtures";
import { loadPreview, stubFetchSequence } from "../../../testing/dialogHarness";
import {
  HEADSHOT_DIR,
  HEADSHOT_SIZES,
  THUMBOR_AUTO_1X,
  THUMBOR_AUTO_SRCSET,
  THUMBOR_MAIN_CROP,
  THUMBOR_MAIN_1X,
  THUMBOR_MAIN_SRCSET,
  THUMBOR_PREVIEW_1X,
  THUMBOR_PREVIEW_SRCSET,
  THUMBOR_SOURCE_HEIGHT,
  THUMBOR_SOURCE_WIDTH,
  headshotCrop,
  payload,
  payloadThumb,
} from "../../../testing/canonicalFixtures";
import {
  cardQuery,
  cleanupDocument,
  flush,
  mountWidget,
  setViewport,
  waitFor,
} from "../../../testing/fixtures";
import type { MountedFixture } from "../../../testing/fixtures";
import { renameRow } from "../../../testing/nestedAdmin";
import { recordWrites } from "../../../testing/writeLog";
import { currentModal, openModalDialog } from "./ModalShell";

const ORIGINAL = `${HEADSHOT_DIR}/original.jpg`;

const WIDGET_CONFIG = {
  csrfToken: "tok",
  urls: {
    index: "/cropduster/",
    upload: "/cropduster/upload/",
    crop: "/cropduster/crop/",
    api: "/cropduster/api/v1/",
  },
};

beforeAll(() => {
  defineWidgetElement();
  installGlobalApi();
});

afterEach(async () => {
  currentModal()?.close();
  await flush();
  await cleanupDocument();
  document.body.removeAttribute("style");
  delete (window as { CropDusterDialog?: unknown }).CropDusterDialog;
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

/** The state the dialog opens on for a widget that already has an image. */
function statePayload() {
  return payload({
    image: {
      id: 1,
      name: ORIGINAL,
      url: `/media/${ORIGINAL}`,
      width: THUMBOR_SOURCE_WIDTH,
      height: THUMBOR_SOURCE_HEIGHT,
    },
    preview: {
      url: THUMBOR_PREVIEW_1X,
      srcset: THUMBOR_PREVIEW_SRCSET,
      file_url: `/media/${HEADSHOT_DIR}/_preview.jpg`,
      width: 421,
      height: 500,
    },
    sizes: HEADSHOT_SIZES,
    thumbs: {
      main: payloadThumb("main", {
        id: 1,
        width: 220,
        height: 180,
        crop: THUMBOR_MAIN_CROP,
        url: `/media/${HEADSHOT_DIR}/main.jpg`,
        rendererUrl: THUMBOR_MAIN_1X,
        srcset: THUMBOR_MAIN_SRCSET,
      }),
      thumb: payloadThumb("thumb", {
        id: 2,
        width: 110,
        height: 90,
        ref: "main",
        refId: 1,
        url: `/media/${HEADSHOT_DIR}/thumb.jpg`,
        rendererUrl: THUMBOR_AUTO_1X,
        srcset: THUMBOR_AUTO_SRCSET,
      }),
    },
  });
}

/** What the crop endpoint answers with once the box has been rendered again. */
function croppedPayload() {
  return headshotCrop({
    image: {
      id: 1,
      name: ORIGINAL,
      url: `/media/${ORIGINAL}`,
      width: THUMBOR_SOURCE_WIDTH,
      height: THUMBOR_SOURCE_HEIGHT,
    },
    preview: {
      url: THUMBOR_PREVIEW_1X,
      srcset: THUMBOR_PREVIEW_SRCSET,
      file_url: `/media/${HEADSHOT_DIR}/_preview.jpg`,
      width: 421,
      height: 500,
    },
    thumbs: {
      main: payloadThumb("main", {
        id: 41,
        width: 220,
        height: 180,
        crop: THUMBOR_MAIN_CROP,
        url: `/media/${HEADSHOT_DIR}/main_tmp.jpg`,
        rendererUrl: THUMBOR_MAIN_1X,
        srcset: THUMBOR_MAIN_SRCSET,
        tmp: true,
        changed: true,
      }),
      thumb: payloadThumb("thumb", {
        id: 42,
        width: 110,
        height: 90,
        ref: "main",
        refId: 41,
        url: `/media/${HEADSHOT_DIR}/thumb_tmp.jpg`,
        rendererUrl: THUMBOR_AUTO_1X,
        srcset: THUMBOR_AUTO_SRCSET,
        tmp: true,
        changed: true,
      }),
    },
  });
}

function widget(options: { prefix?: string } = {}): Promise<MountedFixture> {
  return mountWidget({
    prefix: options.prefix ?? "lead_image",
    image: ORIGINAL,
    imageId: "1",
    sizes: HEADSHOT_SIZES,
    thumbs: [
      { id: 1, name: "main", width: 220, height: 180 },
      { id: 2, name: "thumb", width: 110, height: 90 },
    ],
    config: WIDGET_CONFIG,
  });
}

/** Open the modal by clicking the widget's own button, as an editor does. */
async function openFor(fixture: MountedFixture) {
  fixture.anchor.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  const modal = await waitFor(currentModal, { message: "the modal to open" });
  await waitFor(() => modal.shadow.getElementById("id_image"), {
    message: "the dialog to render",
  });
  return modal;
}

function find<T extends HTMLElement>(id: string): T | null {
  return (currentModal()?.shadow.getElementById(id) as T | null) ?? null;
}

describe("the host", () => {
  const open = () =>
    openModalDialog({
      config: dialogConfig({ sizes: HEADSHOT_SIZES }),
      onComplete: vi.fn(),
    });

  it("is a light-DOM element with an open shadow root", async () => {
    const modal = open();
    await waitFor(() => modal.shadow.getElementById("id_image"), {
      message: "the dialog to render",
    });

    const host = document.querySelector("cropduster-dialog")!;
    expect(host).toBe(modal.host);
    expect(host.parentElement).toBe(document.body);
    expect(host.className).toBe("cropduster-dialog");
    expect(host.getAttribute("data-state")).toBe("open");
    expect(host.shadowRoot?.mode).toBe("open");
    // The dialog's own ids are inside it, where the suite pierces for them.
    expect(modal.shadow.getElementById("id_image")).not.toBeNull();
    expect(modal.shadow.getElementById("crop-button")).toBeNull();
    expect(
      modal.shadow.querySelector("dialog.cropduster-modal-panel"),
    ).not.toBeNull();
  });

  it("opens the panel with showModal, which is what makes it modal", async () => {
    const shown = vi.spyOn(HTMLDialogElement.prototype, "showModal");
    const modal = open();
    await waitFor(() => modal.shadow.getElementById("id_image"), {
      message: "the dialog to render",
    });

    // The browser side of showModal (top layer, inert page, confined tab
    // order, focus handling) is covered by e2e/modal.spec.ts.
    expect(shown).toHaveBeenCalledOnce();
    expect(modal.shadow.querySelector("dialog")?.open).toBe(true);
  });

  it("is one per page: opening again returns the one already open", async () => {
    const first = open();
    await flush();
    const second = open();
    await flush();

    expect(second).toBe(first);
    expect(document.querySelectorAll("cropduster-dialog")).toHaveLength(1);
  });

  it("tears down after a close it did not initiate", async () => {
    const modal = open();
    await waitFor(() => modal.shadow.getElementById("id_image"), {
      message: "the dialog to render",
    });

    // The browser closes the dialog itself on a forced cancel (Escape held
    // down) or a `method="dialog"` form submission; the shell's teardown
    // must still run.
    modal.shadow.querySelector("dialog")!.close();

    await waitFor(() => !modal.host.isConnected, {
      message: "the host to be taken out",
    });
    expect(currentModal()).toBeNull();
    expect(window.CropDusterDialog).toBeUndefined();
  });

  it("says it is closed before it goes, and then goes", async () => {
    const modal = open();
    await flush();

    modal.close();

    // The state flips synchronously; the element is taken out afterwards, so
    // a poller that catches it either way sees no open modal.
    expect(modal.host.getAttribute("data-state")).toBe("closed");
    await waitFor(() => document.querySelector("cropduster-dialog") === null, {
      message: "the host to be taken out",
    });
    expect(currentModal()).toBeNull();
  });

  it("publishes the imperative handle on the page's window", async () => {
    const modal = open();
    await waitFor(() => window.CropDusterDialog, {
      message: "the imperative handle",
    });

    expect(typeof window.CropDusterDialog?.canCommit).toBe("function");

    modal.close();
    await waitFor(() => window.CropDusterDialog === undefined, {
      message: "the handle to be withdrawn",
    });
  });
});

describe("what it takes from the page, and gives back", () => {
  const open = (onComplete = vi.fn()) =>
    openModalDialog({
      config: dialogConfig({ sizes: HEADSHOT_SIZES }),
      onComplete,
    });

  it("locks the body's scroll and restores what it found", async () => {
    document.body.style.overflow = "auto";
    const modal = open();
    await flush();

    expect(document.body.style.overflow).toBe("hidden");

    modal.close();
    await flush();
    expect(document.body.style.overflow).toBe("auto");
  });

  it("leaves no inline overflow behind when there was none", async () => {
    const modal = open();
    await flush();
    modal.close();
    await flush();

    expect(document.body.getAttribute("style")).toBe("");
  });

  it("gives focus back to whatever had it", async () => {
    const opener = document.createElement("button");
    document.body.appendChild(opener);
    opener.focus();

    const modal = open();
    await waitFor(() => document.activeElement === modal.host, {
      message: "the modal to take focus",
    });

    modal.close();
    expect(document.activeElement).toBe(opener);
  });

  // Tab handling is showModal()'s: jsdom implements none of it, so the tab
  // order, its wrap-around, and its skipping of undrawn controls are covered
  // in a real browser by e2e/modal.spec.ts.

  it("swallows the key it closes on", async () => {
    const modal = open();
    await waitFor(() => modal.shadow.getElementById("id_image"), {
      message: "the dialog to render",
    });
    const event = new KeyboardEvent("keydown", {
      key: "Escape",
      bubbles: true,
      cancelable: true,
    });

    // The inert page cannot hold focus, so a real press always starts inside
    // the dialog.
    modal.shadow.querySelector("dialog")!.dispatchEvent(event);

    expect(event.defaultPrevented).toBe(true);
    expect(currentModal()).toBeNull();
  });

  it("leaves Escape to an open source menu, then takes it back", async () => {
    const modal = openModalDialog({
      config: dialogConfig({
        sizes: HEADSHOT_SIZES,
        image: { id: 1, name: ORIGINAL, width: 674, height: 800 },
      }),
      onComplete: vi.fn(),
    });
    const chip = await waitFor(
      () => modal.shadow.getElementById("source-chip"),
      { message: "the source chip to render" },
    );

    chip.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await waitFor(() => modal.shadow.getElementById("source-menu"), {
      message: "the source menu to open",
    });

    // The menu's own handler runs first (it is closer to the target) and
    // stops the press before it bubbles to the shell's handler on the dialog
    // element, so only the menu closes.
    modal.shadow.getElementById("source-menu")?.dispatchEvent(
      new KeyboardEvent("keydown", {
        key: "Escape",
        bubbles: true,
        cancelable: true,
        composed: true,
      }),
    );
    await waitFor(() => !modal.shadow.getElementById("source-menu"), {
      message: "the menu to close",
    });
    expect(currentModal()).toBe(modal);

    // With the menu gone, Escape closes the modal again.
    modal.shadow.querySelector("dialog")!.dispatchEvent(
      new KeyboardEvent("keydown", {
        key: "Escape",
        bubbles: true,
        cancelable: true,
      }),
    );
    await waitFor(() => !modal.host.isConnected, {
      message: "the host to be taken out",
    });
    expect(currentModal()).toBeNull();
  });
});

describe("a dialog that throws while rendering", () => {
  /**
   * A config `hydrateModel` cannot read, which throws inside the initial
   * render rather than in a promise. Every async failure is answered by the
   * reducer; this is the one kind React would otherwise answer by unmounting
   * the tree, leaving the singleton taken and the page unscrollable forever.
   */
  const exploding = () =>
    ({
      ...dialogConfig({ sizes: HEADSHOT_SIZES }),
      get preview(): never {
        throw new Error("boom");
      },
    }) as unknown as ReturnType<typeof dialogConfig>;

  it("gives the page back everything it took, and lets another one open", async () => {
    const logged = vi.spyOn(console, "error").mockImplementation(() => {});
    const opener = document.createElement("button");
    document.body.appendChild(opener);
    opener.focus();
    document.body.style.overflow = "auto";
    const onComplete = vi.fn();

    const modal = openModalDialog({ config: exploding(), onComplete });
    await waitFor(() => currentModal() === null, {
      message: "the failed render to release the singleton",
    });

    expect(modal.host.isConnected).toBe(false);
    expect(document.body.style.overflow).toBe("auto");
    expect(document.activeElement).toBe(opener);
    expect(window.CropDusterDialog).toBeUndefined();
    expect(onComplete).not.toHaveBeenCalled();
    expect(
      logged.mock.calls.some((args) =>
        String(args[0]).includes("failed to render"),
      ),
    ).toBe(true);

    // The singleton was released, so the widget is not permanently broken.
    const next = openModalDialog({
      config: dialogConfig({ sizes: HEADSHOT_SIZES }),
      onComplete: vi.fn(),
    });
    await waitFor(() => next.shadow.querySelector("#dialog-close"), {
      message: "the replacement dialog to render",
    });

    expect(currentModal()).toBe(next);
  });
});

describe("cancelling", () => {
  it("closes on Escape, without writing anything back", async () => {
    const onComplete = vi.fn();
    const modal = openModalDialog({
      config: dialogConfig({ sizes: HEADSHOT_SIZES }),
      onComplete,
    });
    await waitFor(() => modal.shadow.getElementById("id_image"), {
      message: "the dialog to render",
    });

    modal.shadow
      .querySelector("dialog")!
      .dispatchEvent(
        new KeyboardEvent("keydown", { key: "Escape", bubbles: true }),
      );
    await waitFor(() => !modal.host.isConnected, {
      message: "the host to be taken out",
    });

    expect(onComplete).not.toHaveBeenCalled();
  });

  // A press on the native backdrop targets the dialog element itself; the
  // app's content covers the whole panel, so a press inside it targets a
  // descendant.
  it("closes on a click on the backdrop, but not inside the panel", async () => {
    const modal = openModalDialog({
      config: dialogConfig({ sizes: HEADSHOT_SIZES }),
      onComplete: vi.fn(),
    });
    const content = await waitFor(
      () => modal.shadow.querySelector(".cropduster-dialog"),
      { message: "the dialog's content to render" },
    );

    content.dispatchEvent(new MouseEvent("pointerdown", { bubbles: true }));
    content.dispatchEvent(new MouseEvent("pointerup", { bubbles: true }));
    await flush();
    expect(currentModal()).toBe(modal);

    const dialog = modal.shadow.querySelector("dialog")!;
    dialog.dispatchEvent(new MouseEvent("pointerdown", { bubbles: true }));
    dialog.dispatchEvent(new MouseEvent("pointerup", { bubbles: true }));
    await waitFor(() => currentModal() === null, {
      message: "the backdrop click to close the modal",
    });
  });

  it("stays open when a drag from the panel releases over the backdrop", async () => {
    const modal = openModalDialog({
      config: dialogConfig({ sizes: HEADSHOT_SIZES }),
      onComplete: vi.fn(),
    });
    const content = await waitFor(
      () => modal.shadow.querySelector(".cropduster-dialog"),
      { message: "the dialog's content to render" },
    );
    const dialog = modal.shadow.querySelector("dialog")!;

    // A crop drag that overshoots: press inside, release on the backdrop.
    // The browser also synthesizes a click on the backdrop (the common
    // ancestor), which must not dismiss the dialog either.
    content.dispatchEvent(new MouseEvent("pointerdown", { bubbles: true }));
    dialog.dispatchEvent(new MouseEvent("pointerup", { bubbles: true }));
    dialog.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await flush();

    expect(currentModal()).toBe(modal);

    // And the reverse: press on the backdrop, release inside the panel.
    dialog.dispatchEvent(new MouseEvent("pointerdown", { bubbles: true }));
    content.dispatchEvent(new MouseEvent("pointerup", { bubbles: true }));
    await flush();

    expect(currentModal()).toBe(modal);
  });

  it("closes on the close button", async () => {
    const modal = openModalDialog({
      config: dialogConfig({ sizes: HEADSHOT_SIZES }),
      onComplete: vi.fn(),
    });
    const close = await waitFor(
      () => modal.shadow.getElementById("dialog-close"),
      { message: "the close button to render" },
    );

    close.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await waitFor(() => currentModal() === null, {
      message: "the close button to close the modal",
    });
  });
});

describe("opening over a widget", () => {
  it("hydrates from the formset in one round trip", async () => {
    const fetchMock = stubFetchSequence([statePayload()]);
    const fixture = await widget();

    await openFor(fixture);
    await waitFor(
      () => find<HTMLImageElement>("cropbox")?.getAttribute("src"),
      {
        message: "the hydrated preview",
      },
    );

    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, init] = fetchMock.mock.calls[0] as unknown as [
      string,
      RequestInit,
    ];
    expect(url).toBe("/cropduster/api/v1/state/");
    expect(init.method).toBe("POST");
    expect(init.headers).toMatchObject({ "X-CSRFToken": "tok" });
    const body = init.body as URLSearchParams;
    expect(body.get("image")).toBe(ORIGINAL);
    expect(body.get("id")).toBe("1");
    // The crops the formset is bound to, not the image's own.
    expect(body.get("thumbs")).toBe("1,2");
    expect(JSON.parse(body.get("sizes") ?? "[]")).toEqual(HEADSHOT_SIZES);
    expect(body.get("upload_to")).toBe("img/uploads");

    expect(find<HTMLInputElement>("crop-button")?.disabled).toBe(false);
    expect(find<HTMLImageElement>("cropbox")?.getAttribute("src")).toBe(
      THUMBOR_PREVIEW_1X,
    );
    expect(find<HTMLImageElement>("cropbox")?.getAttribute("srcset")).toBe(
      THUMBOR_PREVIEW_SRCSET,
    );
  });

  it("reads as loading until the saved crops arrive", async () => {
    let resolveState!: (response: Response) => void;
    vi.stubGlobal(
      "fetch",
      vi.fn(
        () =>
          new Promise<Response>((resolve) => {
            resolveState = resolve;
          }),
      ),
    );
    const fixture = await widget();
    const modal = await openFor(fixture);

    // The image is on screen (usually straight from cache), but its crop
    // boxes are still in transit: the dialog must read as loading, not as a
    // finished dialog with every crop unset.
    await waitFor(() => find("crop-progress")?.textContent === LOADING_CROPS, {
      message: "the loading progress text",
    });
    expect(find("next-crop-button")).toBeNull();
    expect(find("crop-button")).toBeNull();
    // Drawing a selection needs the crop state the dialog is waiting on.
    expect(modal.shadow.querySelector(".ReactCrop--disabled")).not.toBeNull();
    expect(modal.shadow.querySelector(".cropbox-loading")).not.toBeNull();
    expect(
      modal.shadow.querySelector(".crop-preview")?.getAttribute("aria-label"),
    ).toBe("Main, Crop loading, crop 1 of 1");

    resolveState({
      ok: true,
      status: 200,
      json: () => Promise.resolve(statePayload()),
    } as Response);
    await waitFor(() => find<HTMLInputElement>("crop-button"), {
      message: "the hydrated dialog to offer Save",
    });
    expect(find("crop-progress")?.textContent).toBe("No changes yet");
    expect(modal.shadow.querySelector(".ReactCrop--disabled")).toBeNull();
    expect(
      modal.shadow.querySelector(".crop-preview")?.getAttribute("aria-label"),
    ).toBe("Main, Saved crop available, crop 1 of 1");

    // The veil outlasts hydration while the preview file itself is still in
    // transit, and clears when the file arrives.
    expect(modal.shadow.querySelector(".cropbox-loading")).not.toBeNull();
    loadPreview(find<HTMLImageElement>("cropbox")!, 421, 500);
    await waitFor(
      () => modal.shadow.querySelector(".cropbox-loading") === null,
      { message: "the loading veil to clear" },
    );
  });

  it("asks nothing at all for a widget with no image yet", async () => {
    const fetchMock = stubFetchSequence([statePayload()]);
    const fixture = await mountWidget({
      sizes: HEADSHOT_SIZES,
      config: WIDGET_CONFIG,
    });

    await openFor(fixture);
    await waitFor(() => find("upload-footer"), {
      message: "the upload footer to render",
    });

    expect(fetchMock).not.toHaveBeenCalled();
    expect(find("step-header")).toBeNull();
    expect(find("crop-button")).toBeNull();
    expect(find("upload-footer")?.hidden).toBe(true);
    expect(find("upload-button")?.parentElement?.hidden).toBe(true);
  });
});

describe("completing", () => {
  it("writes the crop into its own widget, in 4.x's order", async () => {
    stubFetchSequence([statePayload(), croppedPayload()]);
    const fixture = await widget();
    const modal = await openFor(fixture);
    await waitFor(
      () => find<HTMLInputElement>("crop-button")?.disabled === false,
      {
        message: "the crop button to come alive",
      },
    );

    const log = recordWrites(fixture.root);
    document.addEventListener(UPDATE_EVENT, (event) => {
      const detail = (event as CustomEvent<{ prefix: string }>).detail;
      log.entries.push(
        `event ${detail.prefix} ` +
          `${(fixture.field("image") as HTMLInputElement).value} ` +
          `${fixture.root.querySelectorAll("option").length}`,
      );
    });

    find<HTMLInputElement>("crop-button")!.dispatchEvent(
      new MouseEvent("click", { bubbles: true }),
    );
    await waitFor(() => modal.host.getAttribute("data-state") === "closed", {
      message: "the crop to land and the modal to take itself down",
    });
    log.stop();

    expect(log.entries).toEqual([
      "value lead_image-0-id=1",
      `value lead_image-0-image=${ORIGINAL}`,
      `value lead_image=${ORIGINAL}`,
      "value lead_image-TOTAL_FORMS=1",
      "option -1",
      "option -2",
      "option +41",
      "option +42",
      `event lead_image ${ORIGINAL} 2`,
    ]);
    // The renditions this session made are the ones the form now contains:
    // `data-url` holds the stored file exactly as 4.x wrote it, and
    // `data-renderer-url` the renderer-routed URL from the crop response.
    expect(
      [...fixture.root.querySelectorAll("option")].map((option) => [
        option.value,
        option.getAttribute("data-url"),
        option.getAttribute("data-renderer-url"),
        option.getAttribute("data-renderer-srcset"),
        option.getAttribute("data-tmp-file"),
      ]),
    ).toEqual([
      [
        "41",
        `/media/${HEADSHOT_DIR}/main_tmp.jpg`,
        THUMBOR_MAIN_1X,
        THUMBOR_MAIN_SRCSET,
        "true",
      ],
      [
        "42",
        `/media/${HEADSHOT_DIR}/thumb_tmp.jpg`,
        THUMBOR_AUTO_1X,
        THUMBOR_AUTO_SRCSET,
        "true",
      ],
    ]);

    // And the modal takes itself down, which is what the suite waits on.
    await waitFor(() => currentModal() === null, {
      message: "the modal to release the singleton",
    });
  });

  it("renders the thumbnail strip from the preview it was given", async () => {
    stubFetchSequence([statePayload(), croppedPayload()]);
    const fixture = await widget();
    await openFor(fixture);
    await waitFor(
      () => find<HTMLInputElement>("crop-button")?.disabled === false,
      {
        message: "the crop button to come alive",
      },
    );

    find<HTMLInputElement>("crop-button")!.dispatchEvent(
      new MouseEvent("click", { bubbles: true }),
    );
    const img = await waitFor(
      () => cardQuery<HTMLImageElement>(fixture.images, "img"),
      { message: "the thumbnail strip to render" },
    );
    expect(img.getAttribute("src")).toBe(THUMBOR_PREVIEW_1X);
    expect(img.getAttribute("srcset")).toBe(THUMBOR_PREVIEW_SRCSET);
    expect(img.getAttribute("width")).toBe("421");
    expect(
      registry.byPrefix("lead_image")?.bridge.getSnapshot().preview,
    ).toMatchObject({
      rendererUrl: THUMBOR_PREVIEW_1X,
      srcset: THUMBOR_PREVIEW_SRCSET,
    });

    // The crop cards display the renderer-routed URLs, not the stored files.
    const cropImg = cardQuery<HTMLImageElement>(
      fixture.images,
      ".cropduster-crop-thumb",
    );
    expect(cropImg?.getAttribute("src")).toBe(THUMBOR_MAIN_1X);
    expect(cropImg?.getAttribute("srcset")).toBe(THUMBOR_MAIN_SRCSET);
  });
});

describe("a row renamed while the modal is up", () => {
  it("delivers to the element it was opened from, not to its old name", async () => {
    stubFetchSequence([statePayload(), croppedPayload()]);
    // Two rows of a nested inline, the second of which is about to be
    // renumbered into the first's place.
    const first = await widget({ prefix: "items-1-image" });
    const second = await widget({ prefix: "items-2-image" });

    const modal = await openFor(first);
    await waitFor(
      () => find<HTMLInputElement>("crop-button")?.disabled === false,
      {
        message: "the crop button to come alive",
      },
    );
    expect(modal.host.getAttribute("data-state")).toBe("open");

    // `_fillGap()`: row 0 was deleted, so 1 becomes 0 and 2 becomes 1. The
    // dialog was opened on `items-1-image`, and that name now belongs to the
    // other widget.
    renameRow(first.container, "items", 1, 0);
    renameRow(second.container, "items", 2, 1);
    await flush();

    const prefixes: string[] = [];
    document.addEventListener(UPDATE_EVENT, (event) => {
      prefixes.push((event as CustomEvent<{ prefix: string }>).detail.prefix);
    });

    find<HTMLInputElement>("crop-button")!.dispatchEvent(
      new MouseEvent("click", { bubbles: true }),
    );
    await waitFor(() => prefixes.length > 0, {
      message: "the crop to be delivered",
    });

    const optionValues = (container: HTMLElement, name: string) =>
      [
        ...container.querySelectorAll<HTMLOptionElement>(
          `[name="${name}"] option`,
        ),
      ].map((option) => option.value);

    // The crop landed on the row the editor opened, which is now `-0-`.
    expect(optionValues(first.container, "items-0-image-0-thumbs")).toEqual([
      "41",
      "42",
    ]);
    // ... and not on the row that inherited its name, which is untouched.
    expect(optionValues(second.container, "items-1-image-0-thumbs")).toEqual([
      "1",
      "2",
    ]);
    // The event names the row as it is called now, not as it was called when
    // the dialog opened.
    expect(prefixes).toEqual(["items-0-image"]);
  });
});

describe("a viewport too small for a modal", () => {
  it("opens the popup instead, and no modal", async () => {
    const restore = setViewport(830, 550);
    const open = vi
      .spyOn(window, "open")
      .mockReturnValue({ focus: vi.fn() } as unknown as Window);
    const fixture = await widget();

    fixture.anchor.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await waitFor(() => open.mock.calls.length > 0, {
      message: "the popup to be opened",
    });

    expect(currentModal()).toBeNull();
    expect(open).toHaveBeenCalledOnce();
    restore();
  });
});
