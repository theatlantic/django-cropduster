import { afterEach, describe, expect, it, vi } from "vitest";

import type { Size } from "../../crop/geometry";
import { mountDialog, typeAndBlur } from "../../testing/dialogHarness";
import { flush, waitFor } from "../../testing/fixtures";
import { cropFixture } from "../../testing/legacyWire";

const standaloneCrop = cropFixture("standalone_crop");
const STANDALONE_SIZES = JSON.parse(
  standaloneCrop.request.post["crop-sizes"] ?? "[]",
) as Size[];

const IMAGE = { id: 1, name: "img/original.jpg", width: 674, height: 800 };

function standalone(options: { sizes?: Size[]; withImage?: boolean } = {}) {
  return mountDialog({
    sizes: options.sizes ?? STANDALONE_SIZES,
    standalone: true,
    elId: null,
    ...(options.withImage === false
      ? {}
      : { image: IMAGE, crops: { crop: { x: 0, y: 0, w: 674, h: 800 } } }),
  });
}

afterEach(async () => {
  document.body.innerHTML = "";
  vi.unstubAllGlobals();
  await flush(5);
});

describe("the standalone size form", () => {
  it("is only in the standalone dialog", async () => {
    const { find } = await mountDialog({
      sizes: STANDALONE_SIZES,
      image: IMAGE,
    });
    expect(find("id_size-width")).toBeNull();
    expect(find("step-header")).not.toBeNull();
  });

  it("stays hidden until there is a crop to size", async () => {
    const { find } = await standalone({ withImage: false });
    expect(find("size")?.hidden).toBe(true);
    expect(find("step-header")).toBeNull();
  });

  it("offers the crop's own dimensions as the placeholder", async () => {
    const { find } = await standalone();

    expect(find("size")?.hidden).toBe(false);
    const width = find<HTMLInputElement>("id_size-width")!;
    const height = find<HTMLInputElement>("id_size-height")!;
    expect(width.value).toBe("");
    expect(height.value).toBe("");
    expect(width.placeholder).toBe("674");
    expect(height.placeholder).toBe("800");
  });

  it("writes a typed width into the size, minimum and all", async () => {
    const { find, view } = await standalone();
    const width = find<HTMLInputElement>("id_size-width")!;

    typeAndBlur(width, "300");
    await waitFor(() => view.CropDusterDialog!.state.sizes[0]?.w === 300, {
      message: "the typed width to land",
    });

    const state = view.CropDusterDialog!.state;
    expect(state.sizes[0]).toMatchObject({ w: 300, min_w: 300 });
    expect(width.value).toBe("300");
    // Changing the size does not move the existing crop.
    expect(state.crops.crop?.box).toEqual({ x: 0, y: 0, w: 674, h: 800 });
    // The height placeholder follows the entered width.
    expect(find<HTMLInputElement>("id_size-height")?.placeholder).toBe("356");
  });

  it("refuses a width the original cannot produce", async () => {
    const { find, view } = await standalone();
    const width = find<HTMLInputElement>("id_size-width")!;

    typeAndBlur(width, "9000");
    await waitFor(() => width.value === "", {
      message: "the field to be reset",
    });

    expect(view.CropDusterDialog!.state.sizes[0]).toMatchObject({ w: null });
  });

  it("refuses a width over the size's own maximum", async () => {
    const capped = STANDALONE_SIZES.map((size) => ({ ...size, max_w: 400 }));
    const { find, view } = await standalone({ sizes: capped });
    const width = find<HTMLInputElement>("id_size-width")!;

    typeAndBlur(width, "500");
    await waitFor(() => width.value === "", {
      message: "the field to be reset",
    });
    expect(view.CropDusterDialog!.state.sizes[0]).toMatchObject({ w: null });

    typeAndBlur(width, "350");
    await waitFor(() => view.CropDusterDialog!.state.sizes[0]?.w === 350, {
      message: "the width under the cap to land",
    });
  });

  it("clears the size when the field is emptied", async () => {
    const { find, view } = await standalone();
    const width = find<HTMLInputElement>("id_size-width")!;

    typeAndBlur(width, "300");
    await waitFor(() => view.CropDusterDialog!.state.sizes[0]?.w === 300, {
      message: "the typed width to land",
    });
    typeAndBlur(width, "");
    await waitFor(() => view.CropDusterDialog!.state.sizes[0]?.w === null, {
      message: "the cleared width to land",
    });

    expect(view.CropDusterDialog!.state.sizes[0]).toMatchObject({ min_w: 1 });
    expect(width.placeholder).toBe("674");
  });
});
