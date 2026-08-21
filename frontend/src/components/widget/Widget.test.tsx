import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { currentModal } from "../dialog/shells/ModalShell";
import { defineWidgetElement } from "../../dom/CropDusterWidgetElement";
import { registry } from "../../dom/registry";
import {
  HEADSHOT_DIR,
  THUMBOR_MAIN_1X,
  THUMBOR_MAIN_SRCSET,
  THUMBOR_PREVIEW_1X,
  THUMBOR_PREVIEW_SRCSET,
  THUMBOR_SOURCE_HEIGHT,
  THUMBOR_SOURCE_WIDTH,
} from "../../testing/canonicalFixtures";
import {
  cardQuery,
  cardQueryAll,
  cleanupDocument,
  flush,
  mountFixture,
  mountWidget,
  waitFor,
  waitForWidget,
} from "../../testing/fixtures";

beforeAll(() => {
  defineWidgetElement();
});

afterEach(async () => {
  await cleanupDocument();
  vi.restoreAllMocks();
});

describe("upload button", () => {
  it("renders the template's markup, once", async () => {
    const fixture = await mountWidget();

    expect(fixture.anchor.innerHTML).toBe(
      '<div class="cropduster-button">Upload Image</div>' +
        '<div style="clear: both; height: 3px;"></div>',
    );
    expect(fixture.anchor.querySelectorAll(".cropduster-button")).toHaveLength(
      1,
    );
  });

  it("opens the dialog for the row it was clicked in", async () => {
    const fixture = await mountWidget({
      uploadTo: "img/uploads/%Y_%m",
      sizes: [],
      config: { dialogMode: "window" },
    });
    const open = vi
      .spyOn(window, "open")
      .mockReturnValue({ focus: vi.fn() } as unknown as Window);

    fixture.anchor
      .querySelector(".cropduster-button")!
      .dispatchEvent(new MouseEvent("click", { bubbles: true }));

    // `encodeURI`, as in 4.x: the strftime escapes in an upload_to come back
    // percent-encoded, and the server decodes them.
    expect(open.mock.calls[0]?.[0]).toBe(
      "/cropduster/?pop=1&upload_to=img/uploads/%25Y_%25m" +
        "&sizes=%5B%5D&el_id=lead_image",
    );
  });

  it("starts the query string when the configured URL has none", async () => {
    const fixture = await mountWidget({
      cropdusterUrl: "/cropduster/",
      uploadTo: "img/x",
      sizes: [],
      config: { dialogMode: "window" },
    });
    const open = vi
      .spyOn(window, "open")
      .mockReturnValue({ focus: vi.fn() } as unknown as Window);

    fixture.anchor.dispatchEvent(new MouseEvent("click", { bubbles: true }));

    expect(open.mock.calls[0]?.[0]).toBe(
      "/cropduster/?upload_to=img/x&sizes=%5B%5D&el_id=lead_image",
    );
  });

  it("sends the click to its own field when two share an admin row", async () => {
    // Two cropduster fields grouped into one `fieldsets` tuple render inside a
    // single `.form-row`, which 4.x resolved to the first data field in it.
    const row = document.createElement("div");
    row.className = "form-row";
    document.body.appendChild(row);
    const first = mountFixture({
      prefix: "lead_image",
      withRow: false,
      config: { dialogMode: "window" },
    });
    const second = mountFixture({
      prefix: "alt_image",
      sizes: [],
      withRow: false,
      config: { dialogMode: "window" },
    });
    row.append(first.container, second.container);
    await waitForWidget(first.container);
    await waitForWidget(second.container);
    const open = vi
      .spyOn(window, "open")
      .mockReturnValue({ focus: vi.fn() } as unknown as Window);

    second.anchor.dispatchEvent(new MouseEvent("click", { bubbles: true }));

    expect(open.mock.calls[0]?.[0]).toContain("&el_id=alt_image");
  });

  it("does not follow the anchor's href", async () => {
    const fixture = await mountWidget({
      sizes: [],
      config: { dialogMode: "window" },
    });
    vi.spyOn(window, "open").mockReturnValue({
      focus: vi.fn(),
    } as unknown as Window);
    const event = new MouseEvent("click", { bubbles: true, cancelable: true });

    fixture.anchor.dispatchEvent(event);

    expect(event.defaultPrevented).toBe(true);
  });

  it("opens a modal when the widget requests one", async () => {
    const fixture = await mountWidget({
      sizes: [],
      config: { dialogMode: "modal" },
    });
    const open = vi
      .spyOn(window, "open")
      .mockReturnValue({ focus: vi.fn() } as unknown as Window);

    fixture.anchor.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    const modal = await waitFor(
      () => document.querySelector("cropduster-dialog"),
      { message: "the modal to open" },
    );

    expect(open).not.toHaveBeenCalled();
    expect(modal.getAttribute("data-state")).toBe("open");
    currentModal()?.close();
    await flush();
  });

  it("opens the modal by default when the viewport can hold one", async () => {
    const fixture = await mountWidget({ sizes: [] });
    const open = vi
      .spyOn(window, "open")
      .mockReturnValue({ focus: vi.fn() } as unknown as Window);

    fixture.anchor.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    const modal = await waitFor(
      () => document.querySelector("cropduster-dialog"),
      { message: "the modal to open" },
    );

    expect(open).not.toHaveBeenCalled();
    expect(modal.getAttribute("data-state")).toBe("open");
    currentModal()?.close();
    await flush();
  });
});

describe("thumbnails", () => {
  it("renders the preview for a saved image", async () => {
    const fixture = await mountWidget({
      image: "img/uploads/photo.jpg",
      previewUrl: "/media/img/uploads/photo_preview.jpg",
      previewW: 640,
      previewH: 400,
    });

    const anchor = cardQuery<HTMLAnchorElement>(fixture.images, "a")!;
    const img = anchor.querySelector("img")!;
    expect(anchor.className).toBe("cropduster-image cropduster-image-preview");
    expect(anchor.getAttribute("target")).toBe("_blank");
    expect(anchor.getAttribute("href")).toBe(
      "/media/img/uploads/photo_preview.jpg",
    );
    expect(img.className).toBe(
      "cropduster-image-thumb cropduster-image-thumb-preview",
    );
    expect(img.getAttribute("src")).toBe(
      "/media/img/uploads/photo_preview.jpg",
    );
    expect(img.getAttribute("width")).toBe("640");
    expect(img.getAttribute("height")).toBe("400");
    expect(img.hasAttribute("srcset")).toBe(false);
  });

  it("uses renderer density candidates when the formset includes them", async () => {
    const stored = `/media/${HEADSHOT_DIR}/_preview.jpg`;
    const fixture = await mountWidget({
      image: `${HEADSHOT_DIR}/original.jpg`,
      origW: THUMBOR_SOURCE_WIDTH,
      origH: THUMBOR_SOURCE_HEIGHT,
      previewUrl: stored,
      previewRendererUrl: THUMBOR_PREVIEW_1X,
      previewSrcset: THUMBOR_PREVIEW_SRCSET,
      previewW: 421,
      previewH: 500,
    });

    const anchor = cardQuery<HTMLAnchorElement>(fixture.images, "a")!;
    const img = anchor.querySelector("img")!;
    // The legacy link remains the stored preview while the displayed image is
    // routed through the configured renderer.
    expect(anchor.getAttribute("href")).toBe(stored);
    expect(img.getAttribute("src")).toBe(THUMBOR_PREVIEW_1X);
    expect(img.getAttribute("srcset")).toBe(THUMBOR_PREVIEW_SRCSET);
  });

  it("reserves each image's display box before its file loads", async () => {
    const fixture = await mountWidget({
      image: "img/uploads/photo.jpg",
      previewUrl: "/media/img/uploads/photo_preview.jpg",
      previewW: 640,
      previewH: 400,
      sizes: [{ name: "main", w: 600, h: 480, label: "Main" }],
      thumbs: [
        {
          id: "7",
          name: "main",
          width: 600,
          height: 480,
          url: "/media/img/uploads/main.jpg",
          tmp: false,
        },
      ],
    });

    // Freshly written renditions have not been fetched yet, so without
    // reserved boxes the card renders bordered dots until they arrive.
    const preview = cardQuery<HTMLImageElement>(
      fixture.images,
      ".cropduster-image-thumb",
    )!;
    // 640x400 under the 180px height cap; the card-width cap stays fluid.
    expect(preview.style.width).toBe("min(100%, 288px)");
    expect(preview.style.aspectRatio).toBe("640 / 400");

    const crop = cardQuery<HTMLImageElement>(
      fixture.images,
      ".cropduster-crop-thumb",
    )!;
    // 600x480 fitted into the rail's 120x64 box.
    expect(crop.style.width).toBe("80px");
    expect(crop.style.height).toBe("64px");
  });

  it("renders nothing without an image", async () => {
    const fixture = await mountWidget({ image: "" });
    expect(cardQuery(fixture.images, ".cropduster-card")).toBeNull();
  });

  it("renders nothing for a name 4.x's path regex rejects", async () => {
    const fixture = await mountWidget({ image: "photo.jpg" });
    expect(cardQuery(fixture.images, ".cropduster-card")).toBeNull();
  });

  it("re-renders when another script writes the image field", async () => {
    const fixture = await mountWidget({ image: "" });

    (fixture.field("image") as HTMLInputElement).value = "img/uploads/new.jpg";
    await waitFor(() => cardQuery(fixture.images, "a"), {
      message: "the thumbnail strip to re-render",
    });

    expect(cardQueryAll(fixture.images, "a")).toHaveLength(1);
  });
});

describe("the summary card", () => {
  const CARD_OPTIONS = {
    image: "img/uploads/a01_G_229/original.jpg",
    origW: 1440,
    origH: 1800,
    sizes: [
      { name: "main", w: 600, h: 480, label: "Main" },
      { name: "no_height", w: 600, label: "No Height" },
    ],
    thumbs: [
      {
        id: "7",
        name: "main",
        width: 600,
        height: 480,
        url: "/media/img/uploads/a01_G_229/main.jpg",
        tmp: false,
      },
    ],
  };

  it("shows the file name, its dimensions and a card per size", async () => {
    const fixture = await mountWidget(CARD_OPTIONS);

    expect(
      cardQuery(fixture.images, ".cropduster-card-filename")?.textContent,
    ).toBe("a01_G_229.jpg");
    expect(
      cardQuery(fixture.images, ".cropduster-card-detail")?.textContent,
    ).toBe("1440 × 1800 · JPEG");

    const crops = cardQueryAll(fixture.images, ".cropduster-crop");
    expect(crops).toHaveLength(2);
    expect(crops[0]?.querySelector("img")?.getAttribute("src")).toBe(
      "/media/img/uploads/a01_G_229/main.jpg",
    );
    expect(crops[0]?.textContent).toContain("Main");
    // `no_height` has no rendition yet: an empty, dashed frame.
    expect(crops[1]?.querySelector("img")).toBeNull();
    expect(crops[1]?.querySelector(".cropduster-crop-pending")).not.toBeNull();
    expect(crops[1]?.textContent).toContain("No Height");
  });

  it("displays a crop from its renderer URL when the markup has one", async () => {
    const fixture = await mountWidget({
      ...CARD_OPTIONS,
      image: `${HEADSHOT_DIR}/original.jpg`,
      origW: THUMBOR_SOURCE_WIDTH,
      origH: THUMBOR_SOURCE_HEIGHT,
      thumbs: [
        {
          ...CARD_OPTIONS.thumbs[0]!,
          url: `/media/${HEADSHOT_DIR}/main.jpg`,
          rendererUrl: THUMBOR_MAIN_1X,
          rendererSrcset: THUMBOR_MAIN_SRCSET,
        },
      ],
    });

    const crops = cardQueryAll(fixture.images, ".cropduster-crop");
    expect(crops[0]?.querySelector("img")?.getAttribute("src")).toBe(
      THUMBOR_MAIN_1X,
    );
    expect(crops[0]?.querySelector("img")?.getAttribute("srcset")).toBe(
      THUMBOR_MAIN_SRCSET,
    );
  });

  it("labels the widget button for editing once an image exists", async () => {
    const fixture = await mountWidget(CARD_OPTIONS);
    expect(
      fixture.anchor.querySelector(".cropduster-button")?.textContent,
    ).toBe("Edit Crops");
  });

  it("stages deletion through the formset's DELETE checkbox", async () => {
    const fixture = await mountWidget(CARD_OPTIONS);
    const checkbox = fixture.field("DELETE") as HTMLInputElement;
    const button = cardQuery<HTMLButtonElement>(
      fixture.images,
      ".cropduster-delete-button",
    )!;
    expect(button.textContent).toBe("Delete image");
    expect(cardQuery(fixture.images, ".cropduster-card-note")).toBeNull();

    button.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await waitFor(() => checkbox.checked, {
      message: "the DELETE checkbox to be staged",
    });
    await waitFor(() => fixture.root.classList.contains("predelete"), {
      message: "the predelete class",
    });

    const undo = cardQuery<HTMLButtonElement>(
      fixture.images,
      ".cropduster-delete-button",
    )!;
    expect(undo.textContent).toBe("Undo delete");
    expect(
      cardQuery(fixture.images, ".cropduster-card-note")?.textContent,
    ).toBe("Removed when the form is saved.");
    expect(
      cardQuery(fixture.images, ".cropduster-card-deleted"),
    ).not.toBeNull();

    undo.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await waitFor(() => !checkbox.checked, {
      message: "the DELETE checkbox to be unstaged",
    });
  });
});

describe("delete state", () => {
  it("tracks the DELETE checkbox on the wrapper", async () => {
    const fixture = await mountWidget();
    const checkbox = fixture.field("DELETE") as HTMLInputElement;

    checkbox.checked = true;
    checkbox.dispatchEvent(new Event("change", { bubbles: true }));
    await waitFor(() => fixture.root.classList.contains("predelete"), {
      message: "the predelete class",
    });
    expect(fixture.root.classList.contains("grp-predelete")).toBe(true);

    // nested-admin's undelete assigns the property and fires nothing.
    checkbox.checked = false;
    await waitFor(() => !fixture.root.classList.contains("predelete"), {
      message: "the predelete class to come off",
    });
  });
});

describe("the uncontrolled formset", () => {
  it("renders no form controls of its own", async () => {
    const fixture = await mountWidget({ image: "img/uploads/photo.jpg" });

    for (const container of [fixture.anchor, fixture.images]) {
      expect(container.querySelectorAll("[name]")).toHaveLength(0);
      expect(container.querySelectorAll("input,select,textarea")).toHaveLength(
        0,
      );
    }
  });

  it("leaves the formset inputs exactly as the server rendered them", async () => {
    const before = mountFixture({ image: "img/uploads/photo.jpg" });
    const names = [...before.root.querySelectorAll("[name]")].map(
      (el) => el.getAttribute("name") ?? "",
    );
    await waitForWidget(before.container);

    expect(
      [...before.root.querySelectorAll("[name]")].map(
        (el) => el.getAttribute("name") ?? "",
      ),
    ).toEqual(names);
    expect(registry.byPrefix("lead_image")).not.toBeNull();
  });
});
