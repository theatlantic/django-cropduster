import { afterEach, describe, expect, it, vi } from "vitest";

import type { Size } from "../../crop/geometry";
import {
  chooseFile,
  mountDialog,
  stubFetch,
} from "../../testing/dialogHarness";
import { flush, waitFor } from "../../testing/fixtures";
import { cropFixture } from "../../testing/legacyWire";
import {
  THUMBOR_PREVIEW_1X,
  THUMBOR_PREVIEW_SRCSET,
} from "../../testing/canonicalFixtures";

const cropSuggest = cropFixture("crop_lead_image_suggest");
const cropHeadshot = cropFixture("crop_author_headshot");

function sizesOf(fixture: { request: { post: Record<string, string> } }) {
  return JSON.parse(fixture.request.post["crop-sizes"] ?? "[]") as Size[];
}

const TWO_SIZES = sizesOf(cropSuggest);
const ONE_SIZE = sizesOf(cropHeadshot);

const IMAGE = {
  id: 1,
  name: "article/lead_image/{Y}/{m}/{DIR}/original.jpg",
  width: 1300,
  height: 1016,
};

function click(el: Element | null) {
  el?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
}

afterEach(async () => {
  document.body.innerHTML = "";
  vi.unstubAllGlobals();
  await flush(5);
});

describe("moving between sizes", () => {
  it("says which size is showing, and disables the ends", async () => {
    const { find } = await mountDialog({ sizes: TWO_SIZES, image: IMAGE });
    const left = find<HTMLButtonElement>("nav-left")!;
    const right = find<HTMLButtonElement>("nav-right")!;

    expect(find("crop-nav")?.hidden).toBe(false);
    expect(find("current-thumb-index")?.textContent).toBe("1");
    expect(find("thumb-total-count")?.textContent).toBe("2");
    expect(find("current-thumb-label")?.textContent).toBe("Main");
    // Preserve both the compatibility class and the native disabled state.
    expect(left.className).toContain("disabled");
    expect(left.disabled).toBe(true);
    expect(right.className).not.toContain("disabled");
    expect(right.disabled).toBe(false);

    click(right);
    await waitFor(() => find("current-thumb-index")?.textContent === "2", {
      message: "the nav to move on",
    });

    expect(find("current-thumb-label")?.textContent).toBe("No Height");
    expect(left.className).not.toContain("disabled");
    expect(left.disabled).toBe(false);
    expect(right.className).toContain("disabled");
    expect(right.disabled).toBe(true);

    right.click();
    await flush();
    expect(find("current-thumb-index")?.textContent).toBe("2");

    click(left);
    await waitFor(() => find("current-thumb-index")?.textContent === "1", {
      message: "the nav to move back",
    });
  });

  it("uses preview presence to communicate crop availability", async () => {
    const { find, shadow } = await mountDialog({
      sizes: TWO_SIZES,
      image: IMAGE,
    });
    const previews = [
      ...shadow.querySelectorAll<HTMLButtonElement>(".crop-preview"),
    ];

    expect(previews).toHaveLength(2);
    expect(previews[0]?.getAttribute("aria-current")).toBe("step");
    expect(previews[0]?.tabIndex).toBe(0);
    expect(previews[0]?.getAttribute("aria-label")).toBe(
      "Main, Crop available, crop 1 of 2",
    );
    expect(previews[0]?.title).toBe("Main");
    const suggested = previews[1]?.querySelector<HTMLElement>(
      ".crop-preview-image",
    );
    expect(suggested?.style.backgroundImage).toBe("");
    expect(suggested?.className).toContain("empty");
    // `no_height` fixes only its width, so its pending placeholder is the
    // plain full-frame rectangle, not a 600:1 sliver.
    expect(suggested?.style.width).toBe("58px");
    expect(suggested?.style.height).toBe("48px");
    expect(previews[1]?.getAttribute("aria-label")).toBe(
      "No Height, No crop yet, crop 2 of 2",
    );
    expect(previews[1]?.querySelector(".crop-preview-status")).toBeNull();
    expect(previews[1]?.querySelector(".crop-preview-label")).toBeNull();

    click(previews[1] ?? null);
    await waitFor(() => find("current-thumb-index")?.textContent === "2", {
      message: "the preview to select its crop",
    });

    expect(previews[0]?.hasAttribute("aria-current")).toBe(false);
    expect(previews[0]?.tabIndex).toBe(-1);
    expect(previews[1]?.getAttribute("aria-current")).toBe("step");
    expect(previews[1]?.tabIndex).toBe(0);
    expect(
      previews[1]
        ?.querySelector<HTMLImageElement>(".crop-preview-image img")
        ?.getAttribute("src"),
    ).toContain("preview.jpg");
  });

  it("draws saved crops from live geometry instead of a stale rendition", async () => {
    const { shadow } = await mountDialog({
      sizes: [TWO_SIZES[0]!],
      image: IMAGE,
      previewRendererUrl: THUMBOR_PREVIEW_1X,
      previewSrcset: THUMBOR_PREVIEW_SRCSET,
      crops: { main: { x: 15, y: 0, w: 1270, h: 1016 } },
      cropThumbs: {
        main: {
          id: 1,
          name: "main",
          width: 600,
          height: 480,
          url: "/media/stale-main.jpg",
        },
      },
    });
    const image = shadow.querySelector<HTMLElement>(".crop-preview-image")!;

    const live = image.querySelector("img")!;
    expect(live.getAttribute("src")).toBe(THUMBOR_PREVIEW_1X);
    expect(live.getAttribute("srcset")).toBe(THUMBOR_PREVIEW_SRCSET);
    expect(live.getAttribute("src")).not.toContain("stale-main.jpg");
    expect(parseFloat(live.style.width)).toBeCloseTo((1300 / 1270) * 100);
    expect(parseFloat(live.style.height)).toBeCloseTo(100);
    expect(parseFloat(live.style.left)).toBeCloseTo((-15 / 1270) * 100);
    expect(parseFloat(live.style.top)).toBeCloseTo(0);
  });

  it("marks a saved crop when its geometry becomes dirty", async () => {
    const { shadow } = await mountDialog({
      sizes: [TWO_SIZES[0]!],
      image: IMAGE,
      crops: { main: { x: 15, y: 0, w: 1270, h: 1016 } },
      cropThumbs: {
        main: {
          id: 1,
          name: "main",
          width: 600,
          height: 480,
          url: "/media/main.jpg",
        },
      },
    });
    const cropbox = shadow.getElementById("cropbox")!;
    cropbox.getBoundingClientRect = () =>
      ({
        x: 0,
        y: 0,
        top: 0,
        right: 800,
        bottom: 500,
        left: 0,
        width: 800,
        height: 500,
        toJSON: () => ({}),
      }) as DOMRect;
    const preview = shadow.querySelector<HTMLButtonElement>(".crop-preview")!;

    expect(preview.hasAttribute("data-dirty")).toBe(false);
    shadow.querySelector(".ReactCrop__crop-selection")?.dispatchEvent(
      new KeyboardEvent("keydown", {
        key: "ArrowRight",
        bubbles: true,
        cancelable: true,
      }),
    );
    await waitFor(() => preview.hasAttribute("data-dirty"), {
      message: "the saved crop to become dirty",
    });

    expect(preview.className).toContain("dirty");
    expect(preview.getAttribute("aria-label")).toBe(
      "Main, Saved crop with unsaved changes, crop 1 of 1",
    );
  });

  /**
   * Use buttons for keyboard navigation and modal focus trapping while
   * retaining the 4.x ids and triangle styling.
   */
  it("offers the arrows to the keyboard", async () => {
    const { find, shadow } = await mountDialog({
      sizes: TWO_SIZES,
      image: IMAGE,
    });
    const left = find<HTMLButtonElement>("nav-left")!;
    const right = find<HTMLButtonElement>("nav-right")!;

    for (const [button, label] of [
      [left, "Previous size"],
      [right, "Next size"],
    ] as const) {
      expect(button.tagName).toBe("BUTTON");
      // The standalone dialog renders inside a form.
      expect(button.type).toBe("button");
      expect(button.getAttribute("aria-label")).toBe(label);
    }

    right.focus();
    expect(shadow.activeElement).toBe(right);
    right.click();
    await waitFor(() => find("current-thumb-index")?.textContent === "2", {
      message: "the nav to move on",
    });

    // The modal focus trap excludes disabled buttons.
    expect(right.matches("button:not([disabled])")).toBe(false);
    right.click();
    await flush();
    expect(find("current-thumb-index")?.textContent).toBe("2");
  });

  it("keeps the single preview and hides only redundant arrows", async () => {
    const { find } = await mountDialog({ sizes: ONE_SIZE, image: IMAGE });

    expect(find("crop-nav")?.hidden).toBe(false);
    expect(find("current-thumb-info")?.hidden).toBe(false);
    expect(find("nav-left")?.hidden).toBe(true);
    expect(find("nav-right")?.hidden).toBe(true);
    expect(find("crop-nav")?.querySelectorAll(".crop-preview")).toHaveLength(1);
  });
});

describe("the crop checklist", () => {
  it("counts progress and offers the next pending size", async () => {
    const { find } = await mountDialog({ sizes: TWO_SIZES, image: IMAGE });

    expect(find("crop-progress")?.textContent).toBe("1 of 2 crops set");
    const next = find<HTMLInputElement>("next-crop-button")!;
    expect(next.value).toBe("Next: No Height →");
    expect(next.disabled).toBe(false);

    click(next);
    await waitFor(() => find("current-thumb-index")?.textContent === "2", {
      message: "the next pending size to become current",
    });

    // Visiting the size seeded its box, so nothing is pending.
    expect(find("crop-progress")?.textContent).toBe("All crops set");
    expect(find("next-crop-button")).toBeNull();
  });

  it("reports a clean reopen as having no changes", async () => {
    const { find } = await mountDialog({
      sizes: TWO_SIZES,
      image: IMAGE,
      crops: {
        main: { x: 15, y: 0, w: 1270, h: 1016 },
        no_height: { x: 15, y: 0, w: 1270, h: 1016 },
      },
    });

    expect(find("crop-progress")?.textContent).toBe("No changes yet");
    expect(find("next-crop-button")).toBeNull();
  });
});

describe("the save button", () => {
  it("is absent until every crop size is populated", async () => {
    const { find } = await mountDialog({ sizes: TWO_SIZES, image: IMAGE });

    expect(find("crop-button")).toBeNull();
    expect(find("next-crop-button")).not.toBeNull();

    click(find("nav-right"));
    const button = await waitFor(() => find<HTMLInputElement>("crop-button"), {
      message: "Save to become available",
    });

    expect(button.value).toBe("Save");
    expect(button.disabled).toBe(false);
    expect(button.className).not.toContain("disabled");
    expect(find("next-crop-button")).toBeNull();
  });

  it("says so while saving, and completes from any selected crop", async () => {
    let resolve: ((value: unknown) => void) | undefined;
    const pending = new Promise((r) => {
      resolve = r;
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        pending.then(() => ({
          ok: true,
          json: () => Promise.resolve(cropSuggest.response),
        })),
      ),
    );

    const { find, shadow, view } = await mountDialog({
      sizes: TWO_SIZES,
      image: IMAGE,
    });

    expect(find("crop-button")).toBeNull();
    click(find("nav-right"));
    const button = await waitFor(() => find<HTMLInputElement>("crop-button"), {
      message: "Save to become available",
    });
    click(find("nav-left"));
    await waitFor(() => find("current-thumb-index")?.textContent === "1", {
      message: "the first crop to be current",
    });

    click(button);
    await waitFor(() => button.value === "Saving...", {
      message: "the in-flight label",
    });

    expect(button.disabled).toBe(true);
    expect(button.className).toContain("disabled");
    expect(view.CropDusterDialog?.canCommit()).toBe(false);
    for (const preview of shadow.querySelectorAll<HTMLButtonElement>(
      ".crop-preview",
    )) {
      expect(preview.disabled).toBe(true);
      expect(preview.className).toContain("disabled");
    }
    expect(find<HTMLButtonElement>("source-chip")?.disabled).toBe(true);

    resolve?.(undefined);
    await waitFor(() => view.close.mock.calls.length === 1, {
      message: "the completed save to close the dialog",
    });

    expect(find("crop-button")).toBeNull();
    for (const preview of shadow.querySelectorAll<HTMLButtonElement>(
      ".crop-preview",
    )) {
      expect(preview.disabled).toBe(true);
      expect(preview.className).toContain("disabled");
    }
  });

  it("is inert before there is anything to crop", async () => {
    const { find } = await mountDialog({ sizes: TWO_SIZES });

    expect(find("crop-button")).toBeNull();
    expect(find("crop-footer")?.hidden).toBe(true);
  });
});

describe("replacing the image", () => {
  it("stages a replacement from the source menu, and Cancel backs out", async () => {
    const { find, shadow, view } = await mountDialog({
      sizes: TWO_SIZES,
      image: IMAGE,
    });

    const chip = find<HTMLButtonElement>("source-chip")!;
    expect(chip.disabled).toBe(false);
    expect(find("source-menu")).toBeNull();
    expect(find("reupload-button")?.parentElement?.hidden).toBe(true);

    click(chip);
    await waitFor(() => find("source-menu"), {
      message: "the source menu to open",
    });

    click(find("replace-image-menuitem"));
    await waitFor(() => find("upload-footer")?.hidden === false, {
      message: "the replace stage to appear",
    });

    expect(find("step-header")?.textContent).toBe("Replace the image");
    expect(shadow.getElementById("replace-image-help")?.textContent).toBe(
      "Crops for all 2 sizes will be redone after the new image uploads.",
    );
    expect(find("crop-footer")?.hidden).toBe(true);
    expect(find("image-container")?.hidden).toBe(true);
    expect(find("crop-nav")?.hidden).toBe(true);
    expect(find<HTMLInputElement>("upload-button")?.disabled).toBe(true);
    expect(find("upload-button")?.parentElement?.hidden).toBe(true);
    expect(
      shadow.querySelector(".cropduster-dialog")?.getAttribute("data-stage"),
    ).toBe("upload");
    // Nothing is reset until a replacement upload actually lands.
    expect(
      shadow.querySelector(".cropduster-dialog")?.hasAttribute("data-image"),
    ).toBe(true);
    expect(view.CropDusterDialog?.state.sources.primary?.name).toBe(IMAGE.name);
    expect(view.CropDusterDialog?.state.crops.main?.box).not.toBeNull();

    click(find("cancel-replace-button"));
    await waitFor(() => find("crop-footer")?.hidden === false, {
      message: "the crop stage to return",
    });

    expect(find("step-header")?.textContent).toBe("Set crop: Main");
    expect(view.CropDusterDialog?.state.crops.main?.box).not.toBeNull();
  });

  it("uploads a replacement as soon as it is chosen", async () => {
    const fetchMock = stubFetch(cropHeadshot.response);
    const { find } = await mountDialog({ sizes: TWO_SIZES, image: IMAGE });

    click(find("source-chip"));
    await waitFor(() => find("source-menu"), {
      message: "the source menu to open",
    });
    click(find("replace-image-menuitem"));
    await waitFor(() => find("replace-image-help"), {
      message: "the replace stage to appear",
    });

    const input = find<HTMLInputElement>("id_image")!;
    chooseFile(input, "replacement.jpg");
    await waitFor(() => fetchMock.mock.calls.length === 1, {
      message: "the replacement upload request",
    });
    expect(fetchMock).toHaveBeenCalledOnce();
    expect(find("upload-button")?.parentElement?.hidden).toBe(true);

    const [url, init] = fetchMock.mock.calls[0] as unknown as [
      string,
      RequestInit,
    ];
    expect(url).toBe("/cropduster/api/v1/upload/");
    expect((init.body as FormData).get("image")).toMatchObject({
      name: "replacement.jpg",
    });
  });

  it("keeps the hidden legacy re-upload action functional", async () => {
    const fetchMock = stubFetch(cropHeadshot.response);
    const { find } = await mountDialog({ sizes: TWO_SIZES, image: IMAGE });
    const legacy = find<HTMLInputElement>("reupload-button")!;

    expect(legacy.parentElement?.hidden).toBe(true);
    expect(legacy.disabled).toBe(true);

    const input = find<HTMLInputElement>("id_image")!;
    Object.defineProperty(input, "files", {
      value: [new File(["x"], "replacement.jpg")],
      configurable: true,
    });
    input.dispatchEvent(new Event("change", { bubbles: true }));
    await waitFor(() => !legacy.disabled, {
      message: "the legacy action to follow its staged file",
    });

    click(legacy);
    await waitFor(() => fetchMock.mock.calls.length === 1, {
      message: "the legacy re-upload request",
    });
  });
});
