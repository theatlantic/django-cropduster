import { afterEach, describe, expect, it, vi } from "vitest";

import { flush, waitFor } from "../../../testing/fixtures";
import { dialogConfigJson } from "../../../testing/dialogFixtures";
import {
  apiError,
  chooseFile,
  fakeView,
  loadPreview,
  mountDialog,
  stubFetch,
} from "../../../testing/dialogHarness";
import type { OpenerStub } from "../../../testing/dialogHarness";
import {
  CACHE_BUSTER,
  HEADSHOT_DIR,
  HEADSHOT_SIZES,
  THUMBOR_MAIN_1X,
  THUMBOR_MAIN_SRCSET,
  THUMBOR_PREVIEW_1X,
  THUMBOR_PREVIEW_SRCSET,
  THUMBOR_SOURCE_HEIGHT,
  THUMBOR_SOURCE_WIDTH,
  headshotCrop,
  headshotUpload,
  thumborHeadshotCrop,
} from "../../../testing/canonicalFixtures";
import { mountPageShell } from "./PageShell";

afterEach(async () => {
  document.body.innerHTML = "";
  delete (window as { CropDusterDialog?: unknown }).CropDusterDialog;
  vi.unstubAllGlobals();
  await flush(5);
});

describe("mounting", () => {
  it("renders into an open shadow root, with the 4.x dialog ids in it", async () => {
    const { host, find, shadow } = await mountDialog({ sizes: HEADSHOT_SIZES });

    expect(host.shadowRoot).not.toBeNull();
    expect(host.shadowRoot?.mode).toBe("open");
    // Keep the app out of the light DOM so Grappelli styles do not apply.
    expect(host.children).toHaveLength(0);

    for (const id of [
      "id_image",
      "upload-min-size-help",
      "error-container",
      "cropbox",
      "crop-nav",
      "nav-left",
      "nav-right",
      "current-thumb-info",
      "current-thumb-index",
      "thumb-total-count",
      "current-thumb-label",
      "upload-footer",
      "upload-button",
      "crop-footer",
      "crop-progress",
      "reupload-button",
    ]) {
      expect([id, find(id) !== null]).toEqual([id, true]);
    }
    expect(find("step-header")).toBeNull();
    expect(find("primary-image-help")).toBeNull();
    expect(shadow.querySelector(".upload-stage-copy")).toBeNull();
    expect(find("crop-button")).toBeNull();
    expect(shadow.querySelector(".upload-file-title")?.textContent).toBe(
      "Upload an image",
    );
    expect(find<HTMLImageElement>("cropbox")?.hasAttribute("srcset")).toBe(
      false,
    );
    expect(find("upload-footer")?.hidden).toBe(true);
    expect(find("upload-button")?.parentElement?.hidden).toBe(true);
    expect(shadow.querySelector("style, [data-styles]")).not.toBe(undefined);
  });

  it("mounts once per host", async () => {
    const { host, shadow } = await mountDialog({ sizes: HEADSHOT_SIZES });
    const first = shadow.innerHTML;

    mountPageShell(host, { view: fakeView({}) });
    await flush();

    expect(shadow.querySelectorAll(".cropduster-dialog-root")).toHaveLength(1);
    expect(shadow.innerHTML).toBe(first);
  });

  it("advertises the smallest usable upload", async () => {
    const { find } = await mountDialog({ sizes: HEADSHOT_SIZES });
    expect(find("upload-min-size-help")?.textContent).toBe(
      "Min. size: 220 x 180",
    );
  });
});

describe("the upload step", () => {
  it("uploads as soon as a file is chosen", async () => {
    const fetchMock = stubFetch(headshotUpload());
    const { find, host, shadow } = await mountDialog({
      sizes: HEADSHOT_SIZES,
      elId: "headshot",
      uploadTo: "author/headshots/%Y/%m",
    });

    expect(find("step-header")).toBeNull();
    expect(find("primary-image-help")).toBeNull();
    expect(shadow.querySelector(".upload-stage-copy")).toBeNull();
    expect(shadow.querySelector(".upload-file-title")?.textContent).toBe(
      "Upload an image",
    );
    expect(find("upload-footer")?.hidden).toBe(true);
    expect(find("upload-button")?.parentElement?.hidden).toBe(true);
    expect(find("crop-footer")?.hidden).toBe(true);
    expect(find("crop-button")).toBeNull();
    expect(find("image-container")?.hidden).toBe(true);
    expect(find("crop-nav")?.hidden).toBe(true);
    expect(host.getAttribute("data-phase")).toBe("upload");
    expect(host.hasAttribute("data-image")).toBe(false);
    expect(
      shadow.querySelector(".cropduster-dialog")?.getAttribute("data-phase"),
    ).toBe("upload");

    chooseFile(find<HTMLInputElement>("id_image")!);
    await waitFor(() => fetchMock.mock.calls.length > 0, {
      message: "the upload request",
    });
    expect(fetchMock).toHaveBeenCalledOnce();

    const [url, init] = fetchMock.mock.calls[0] as unknown as [
      string,
      RequestInit,
    ];
    expect(url).toBe("/cropduster/api/v1/upload/");
    const body = init.body as FormData;
    expect(body.get("upload_to")).toBe("author/headshots/%Y/%m");
    expect(JSON.parse(String(body.get("sizes")))).toEqual(HEADSHOT_SIZES);

    await waitFor(() => host.getAttribute("data-phase") === "crop", {
      message: "the crop step",
    });
    expect(shadow.activeElement).toBe(find("step-header"));
    expect(find("upload-footer")?.hidden).toBe(true);
    expect(find("crop-footer")?.hidden).toBe(false);
    expect(find("image-container")?.hidden).toBe(false);
    expect(find("crop-nav")?.hidden).toBe(false);
    expect(host.getAttribute("data-phase")).toBe("crop");
    expect(host.hasAttribute("data-image")).toBe(true);
    expect(host.hasAttribute("data-file")).toBe(false);
    expect(find<HTMLImageElement>("cropbox")?.getAttribute("src")).toBe(
      `/media/${HEADSHOT_DIR}/_preview.jpg${CACHE_BUSTER}`,
    );
  });

  it("shows the server's message as text and stays on the upload step", async () => {
    const fetchMock = stubFetch(
      apiError(
        "image_too_small",
        "The image is 255x80; it has to be at least 220x180.",
        { field: "image" },
      ),
      { status: 400 },
    );
    const { find, shadow } = await mountDialog({ sizes: HEADSHOT_SIZES });

    chooseFile(find<HTMLInputElement>("id_image")!);
    const container = await waitFor(
      () =>
        find("error-container")?.hidden === false
          ? find("error-container")
          : null,
      { message: "the error banner" },
    );
    expect(fetchMock).toHaveBeenCalledOnce();

    const note = container.querySelector(".errornote")!;
    expect(note.textContent).toBe(
      "The image is 255x80; it has to be at least 220x180.",
    );
    // Render the server message as text rather than HTML.
    expect(note.children).toHaveLength(0);
    expect(find("error-container")?.getAttribute("role")).toBe("alert");
    expect(shadow.activeElement).toBe(find("id_image"));
    expect(find("upload-footer")?.hidden).toBe(true);
    expect(find("upload-button")?.parentElement?.hidden).toBe(true);
  });

  it("keeps standalone upload behind its explicit action", async () => {
    const fetchMock = stubFetch(headshotUpload());
    const { find } = await mountDialog({
      sizes: HEADSHOT_SIZES,
      standalone: true,
    });
    const button = find<HTMLInputElement>("upload-button")!;

    expect(find("upload-footer")?.hidden).toBe(false);
    expect(button.disabled).toBe(true);

    chooseFile(find<HTMLInputElement>("id_image")!);
    await waitFor(() => !button.disabled, {
      message: "the standalone Upload action to become available",
    });
    expect(fetchMock).not.toHaveBeenCalled();

    button.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await waitFor(() => fetchMock.mock.calls.length === 1, {
      message: "the standalone upload request",
    });
    const [, init] = fetchMock.mock.calls[0] as unknown as [
      string,
      RequestInit,
    ];
    const body = init.body as FormData;
    expect(body.get("standalone")).toBe("1");
  });

  it("keeps a failed standalone upload staged for retry", async () => {
    const fetchMock = stubFetch(
      apiError("image_too_small", "The image is too small.", {
        field: "image",
      }),
      { status: 400 },
    );
    const { find } = await mountDialog({
      sizes: HEADSHOT_SIZES,
      standalone: true,
    });
    const button = find<HTMLInputElement>("upload-button")!;

    chooseFile(find<HTMLInputElement>("id_image")!);
    await waitFor(() => !button.disabled, {
      message: "the standalone Upload action to become available",
    });
    button.dispatchEvent(new MouseEvent("click", { bubbles: true }));

    await waitFor(
      () =>
        find("error-container")?.hidden === false && button.disabled === false,
      { message: "the failed standalone upload to become retryable" },
    );
    expect(fetchMock).toHaveBeenCalledOnce();

    await flush();
    button.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await waitFor(() => fetchMock.mock.calls.length === 2, {
      message: "the standalone upload retry",
    });
  });
});

describe("CropDusterDialog", () => {
  const openedOnAnImage = () =>
    mountDialog({
      sizes: HEADSHOT_SIZES,
      elId: "headshot",
      image: {
        id: 1,
        name: `${HEADSHOT_DIR}/original.jpg`,
        width: 674,
        height: 800,
      },
    });

  it("is installed on the dialog's own window", async () => {
    const { view } = await openedOnAnImage();
    expect(typeof view.CropDusterDialog?.commit).toBe("function");
    expect(view.CropDusterDialog?.canCommit()).toBe(true);
    expect(view.CropDusterDialog?.state.phase).toBe("crop");
  });

  it("cannot commit before there is an image", async () => {
    const { view } = await mountDialog({ sizes: HEADSHOT_SIZES });
    expect(view.CropDusterDialog?.canCommit()).toBe(false);
  });

  it("commits the same crop as the button, and returns the legacy payload", async () => {
    const fetchMock = stubFetch(thumborHeadshotCrop());
    const { view, opener } = await mountDialog({
      sizes: HEADSHOT_SIZES,
      elId: "headshot",
      image: {
        id: 1,
        name: `${HEADSHOT_DIR}/original.jpg`,
        width: THUMBOR_SOURCE_WIDTH,
        height: THUMBOR_SOURCE_HEIGHT,
      },
    });

    view.CropDusterDialog!.commit();
    await waitFor(() => fetchMock.mock.calls.length > 0, {
      message: "the crop request",
    });

    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, init] = fetchMock.mock.calls[0] as unknown as [
      string,
      RequestInit,
    ];
    expect(url).toBe("/cropduster/api/v1/crop/");
    expect(JSON.parse(String(init.body))).toMatchObject({
      image: { name: `${HEADSHOT_DIR}/original.jpg` },
      standalone: false,
      thumbs: { main: { changed: true, source: null } },
    });

    // The opener receives the 4.x `CropDuster.complete()` payload.
    expect(opener.CropDuster?.complete).toHaveBeenCalledOnce();
    const [prefix, payload, rendererMedia] =
      opener.CropDuster!.complete.mock.calls[0]!;
    expect(prefix).toBe("headshot");
    expect(payload).toMatchObject({
      crop: {
        orig_image: `${HEADSHOT_DIR}/original.jpg`,
        orig_w: THUMBOR_SOURCE_WIDTH,
        orig_h: THUMBOR_SOURCE_HEIGHT,
        thumbs: {
          main: { id: 1, name: "main", width: 220, height: 180 },
          thumb: { id: 2, name: "thumb" },
        },
      },
      initial: true,
      preview_url: `/media/${HEADSHOT_DIR}/_preview.jpg`,
    });
    expect(rendererMedia).toMatchObject({
      preview: {
        url: THUMBOR_PREVIEW_1X,
        srcset: THUMBOR_PREVIEW_SRCSET,
      },
      thumbs: {
        main: { url: THUMBOR_MAIN_1X, srcset: THUMBOR_MAIN_SRCSET },
      },
    });
    expect(view.close).toHaveBeenCalledOnce();
  });

  it("prefers the callback CKEditor registered", async () => {
    stubFetch(headshotCrop());
    const callback = vi.fn();
    const host = document.createElement("div");
    host.id = "cropduster-app";
    host.setAttribute(
      "data-config",
      dialogConfigJson({
        sizes: HEADSHOT_SIZES,
        standalone: true,
        elId: null,
        callbackFn: "cropduster_uiElement_callback",
        image: { id: 1, name: "img/original.jpg", width: 674, height: 800 },
      }),
    );
    document.body.appendChild(host);
    const opener: OpenerStub = {
      CropDuster: { complete: vi.fn() },
      cropduster_uiElement_callback: callback,
    };
    const view = fakeView(opener);
    mountPageShell(host, { view });
    await waitFor(() => view.CropDusterDialog, {
      message: "the dialog to publish its handle",
    });

    view.CropDusterDialog!.commit();
    await waitFor(() => callback.mock.calls.length > 0, {
      message: "the CKEditor callback",
    });

    expect(callback).toHaveBeenCalledOnce();
    expect(callback.mock.calls[0]?.[0]).toBe("cropduster_uiElement_callback");
    // The CKEditor callback retains its exact 4.x two-argument signature.
    expect(callback.mock.calls[0]).toHaveLength(2);
    expect(opener.CropDuster?.complete).not.toHaveBeenCalled();
  });
});

describe("the crop canvas", () => {
  it("uses the renderer preview and its density candidates", async () => {
    const { find } = await mountDialog({
      sizes: HEADSHOT_SIZES,
      image: {
        id: 1,
        name: `${HEADSHOT_DIR}/original.jpg`,
        width: THUMBOR_SOURCE_WIDTH,
        height: THUMBOR_SOURCE_HEIGHT,
      },
      previewRendererUrl: THUMBOR_PREVIEW_1X,
      previewSrcset: THUMBOR_PREVIEW_SRCSET,
    });

    const image = find<HTMLImageElement>("cropbox")!;
    expect(image.getAttribute("src")).toBe(THUMBOR_PREVIEW_1X);
    expect(image.getAttribute("srcset")).toBe(THUMBOR_PREVIEW_SRCSET);
  });

  it("maps the preview's pixels back onto the original", async () => {
    const { find, view } = await mountDialog({
      sizes: HEADSHOT_SIZES,
      image: {
        id: 1,
        name: `${HEADSHOT_DIR}/original.jpg`,
        width: 674,
        height: 800,
      },
    });

    loadPreview(find<HTMLImageElement>("cropbox")!, 421, 500);
    await waitFor(
      () => view.CropDusterDialog!.state.sources.primary?.displayWidth === 421,
      { message: "the preview's dimensions to land" },
    );

    const state = view.CropDusterDialog!.state;
    expect(state.sources.primary?.displayHeight).toBe(500);
    // Loading the preview must not recalculate the source-pixel crop.
    expect(state.crops.main?.box).toEqual({ x: 0, y: 125, w: 674, h: 551 });
  });

  it("reserves the preview's reported box until its file loads", async () => {
    const { find, shadow } = await mountDialog({
      sizes: HEADSHOT_SIZES,
      image: {
        id: 1,
        name: `${HEADSHOT_DIR}/original.jpg`,
        width: 674,
        height: 800,
      },
    });

    // jsdom never fetches the file, so this is the in-transit state: the
    // config's 800x500 preview box held open under a neutral fill and the
    // loading veil, instead of an element collapsed to nothing under the
    // crop selection.
    const image = find<HTMLImageElement>("cropbox")!;
    expect(image.style.width).toBe("800px");
    expect(image.style.height).toBe("500px");
    expect(image.style.backgroundColor).not.toBe("");
    expect(shadow.querySelector(".cropbox-loading")).not.toBeNull();

    loadPreview(image, 421, 500);
    await waitFor(() => image.style.width === "", {
      message: "the reservation to come off",
    });
    expect(image.style.backgroundColor).toBe("");
    expect(shadow.querySelector(".cropbox-loading")).toBeNull();
  });

  it("shows the uploaded file itself until the server preview arrives", async () => {
    const objectUrls = URL as unknown as {
      createObjectURL?: (blob: Blob) => string;
      revokeObjectURL?: (url: string) => void;
    };
    objectUrls.createObjectURL = vi.fn(() => "blob:vitest/0");
    objectUrls.revokeObjectURL = vi.fn();
    try {
      stubFetch(headshotUpload());
      const { find } = await mountDialog({ sizes: HEADSHOT_SIZES });

      chooseFile(find<HTMLInputElement>("id_image")!);
      const image = await waitFor(
        () => {
          const img = find<HTMLImageElement>("cropbox");
          return img?.style.backgroundImage ? img : null;
        },
        { message: "the uploaded file's stand-in background" },
      );

      expect(image.style.backgroundImage).toContain("blob:vitest/0");
      // The upload response reports the preview rendition as 421x500.
      expect(image.style.width).toBe("421px");
      expect(image.style.height).toBe("500px");

      loadPreview(image, 421, 500);
      await waitFor(() => image.style.backgroundImage === "", {
        message: "the stand-in to come off",
      });
    } finally {
      delete objectUrls.createObjectURL;
      delete objectUrls.revokeObjectURL;
    }
  });

  it("constrains the preview to the image well as its height changes", async () => {
    const { find } = await mountDialog({
      sizes: HEADSHOT_SIZES,
      image: {
        id: 1,
        name: `${HEADSHOT_DIR}/original.jpg`,
        width: 674,
        height: 800,
      },
    });
    const container = find("image-container")!;
    const image = find<HTMLImageElement>("cropbox")!;
    const width = 320;
    let height = 240;
    Object.defineProperties(container, {
      clientWidth: { configurable: true, get: () => width },
      clientHeight: { configurable: true, get: () => height },
    });

    const style = getComputedStyle(container);
    const horizontalPadding =
      Number.parseFloat(style.paddingLeft || "0") +
      Number.parseFloat(style.paddingRight || "0");
    const verticalPadding =
      Number.parseFloat(style.paddingTop || "0") +
      Number.parseFloat(style.paddingBottom || "0");

    window.dispatchEvent(new Event("resize"));
    await waitFor(
      () => image.style.maxHeight === `${height - verticalPadding}px`,
      {
        message: "the initial image-well constraint",
      },
    );
    expect(image.style.maxWidth).toBe(`${width - horizontalPadding}px`);

    height = 140;
    window.dispatchEvent(new Event("resize"));
    await waitFor(
      () => image.style.maxHeight === `${height - verticalPadding}px`,
      {
        message: "the reduced image-well constraint",
      },
    );
    expect(image.style.maxWidth).toBe(`${width - horizontalPadding}px`);
  });
});
