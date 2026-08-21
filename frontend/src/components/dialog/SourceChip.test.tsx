import { afterEach, describe, expect, it, vi } from "vitest";

import { mountDialog } from "../../testing/dialogHarness";
import { flush, waitFor } from "../../testing/fixtures";
import { cropFixture } from "../../testing/legacyWire";
import type { Size } from "../../crop/geometry";
import { displayFilename, middleTruncate } from "../../lib/filename";

const TWO_SIZES = JSON.parse(
  cropFixture("crop_lead_image_suggest").request.post["crop-sizes"] ?? "[]",
) as Size[];

const IMAGE = {
  id: 1,
  name: "article/lead_image/{Y}/{m}/a01_G_2291559123/original.jpg",
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

describe("displayFilename", () => {
  it("presents the upload directory's name over the stored original.EXT", () => {
    expect(
      displayFilename("article/lead_image/2026/08/a01_G_229/original.jpg"),
    ).toBe("a01_G_229.jpg");
    expect(displayFilename("a01_G_229/original.png")).toBe("a01_G_229.png");
  });

  it("passes through names that are not stored as original.EXT", () => {
    expect(displayFilename("uploads/portrait-alt.jpg")).toBe(
      "portrait-alt.jpg",
    );
    // No parent directory to take a name from.
    expect(displayFilename("original.jpg")).toBe("original.jpg");
    // An extensionless "original" still answers to its directory's name.
    expect(displayFilename("uploads/original")).toBe("uploads");
  });
});

describe("middleTruncate", () => {
  it("keeps short names and truncates long ones from the middle", () => {
    expect(middleTruncate("short.jpg")).toBe("short.jpg");
    const long = middleTruncate("a-very-long-image-file-name-here.jpg", 24);
    expect(long).toHaveLength(24);
    expect(long).toContain("…");
    expect(long.startsWith("a-very-long-")).toBe(true);
    expect(long.endsWith("here.jpg")).toBe(true);
  });
});

describe("the source chip", () => {
  it("names the image and is absent without one", async () => {
    const bare = await mountDialog({ sizes: TWO_SIZES });
    expect(bare.find("source-chip")).toBeNull();
    document.body.innerHTML = "";

    const { find } = await mountDialog({ sizes: TWO_SIZES, image: IMAGE });
    const chip = find<HTMLButtonElement>("source-chip")!;

    expect(chip.getAttribute("aria-haspopup")).toBe("menu");
    expect(chip.getAttribute("aria-expanded")).toBe("false");
    expect(chip.title).toBe("a01_G_2291559123.jpg");
    // 20 characters fit whole; only longer names are middle-truncated.
    expect(chip.textContent).toBe("Image:a01_G_2291559123.jpg");
    expect(find("source-menu")).toBeNull();
  });

  it("opens a menu with the file's metadata and actions", async () => {
    const { find, shadow } = await mountDialog({
      sizes: TWO_SIZES,
      image: IMAGE,
    });
    const chip = find<HTMLButtonElement>("source-chip")!;

    click(chip);
    await waitFor(() => find("source-menu"), {
      message: "the source menu to open",
    });

    expect(chip.getAttribute("aria-expanded")).toBe("true");
    const meta = shadow.querySelector(".source-menu-meta");
    expect(meta?.textContent).toContain("a01_G_2291559123.jpg");
    expect(meta?.textContent).toContain("1300 × 1016 · JPEG");

    const replace = find<HTMLButtonElement>("replace-image-menuitem")!;
    expect(replace.getAttribute("role")).toBe("menuitem");
    expect(replace.textContent).toContain("Replace the image…");
    expect(replace.textContent).toContain("Resets all crops.");

    const view = find<HTMLAnchorElement>("view-full-size-menuitem")!;
    expect(view.getAttribute("href")).toBe(`/media/${IMAGE.name}`);
    expect(view.target).toBe("_blank");
  });

  it("closes on Escape without closing anything else", async () => {
    const { find } = await mountDialog({ sizes: TWO_SIZES, image: IMAGE });
    const chip = find<HTMLButtonElement>("source-chip")!;

    click(chip);
    await waitFor(() => find("source-menu"), {
      message: "the source menu to open",
    });

    find("source-menu")?.dispatchEvent(
      new KeyboardEvent("keydown", {
        key: "Escape",
        bubbles: true,
        cancelable: true,
      }),
    );
    await waitFor(() => !find("source-menu"), {
      message: "the menu to close",
    });

    expect(chip.getAttribute("aria-expanded")).toBe("false");
  });

  it("closes when a click lands outside it, swallowing that click", async () => {
    const { find } = await mountDialog({ sizes: TWO_SIZES, image: IMAGE });

    click(find("source-chip"));
    await waitFor(() => find("source-menu"), {
      message: "the source menu to open",
    });

    const outside = new MouseEvent("click", {
      bubbles: true,
      cancelable: true,
    });
    document.body.dispatchEvent(outside);
    await waitFor(() => !find("source-menu"), {
      message: "the menu to close",
    });

    expect(outside.defaultPrevented).toBe(true);
  });

  it("opens from the keyboard with ArrowDown", async () => {
    const { find } = await mountDialog({ sizes: TWO_SIZES, image: IMAGE });
    const chip = find<HTMLButtonElement>("source-chip")!;

    chip.dispatchEvent(
      new KeyboardEvent("keydown", {
        key: "ArrowDown",
        bubbles: true,
        cancelable: true,
      }),
    );
    await waitFor(() => find("source-menu"), {
      message: "the source menu to open",
    });

    expect(chip.getAttribute("aria-expanded")).toBe("true");
  });
});
