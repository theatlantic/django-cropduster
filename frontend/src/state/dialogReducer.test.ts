import { describe, expect, it } from "vitest";

import type { Size } from "../crop/geometry";
import { dialogConfig } from "../testing/dialogFixtures";
import {
  CACHE_BUSTER,
  HEADSHOT_SIZES,
  LEAD_IMAGE_SIZES,
  STANDALONE_SIZES,
  THUMBOR_MAIN_1X,
  THUMBOR_MAIN_SRCSET,
  headshotCrop,
  headshotUpload,
  leadImageSuggestion,
  payload,
  payloadThumb,
  standaloneCrop,
  standaloneUpload,
} from "../testing/canonicalFixtures";
import { dialogReducer, primarySource } from "./dialogReducer";
import type { DialogAction, DialogFailure, DialogModel } from "./dialogReducer";

function run(model: DialogModel, ...actions: DialogAction[]): DialogModel {
  return actions.reduce(dialogReducer, model);
}

/** A failure without a structured v1 error object. */
function failure(message: string): DialogFailure {
  return { message, code: null, field: null };
}

function start(options: Parameters<typeof dialogConfig>[0]): DialogModel {
  return dialogReducer(undefined as unknown as DialogModel, {
    type: "hydrate",
    config: dialogConfig(options),
  });
}

describe("the happy path", () => {
  it("merges page-config renderer data into the saved crop", () => {
    const model = start({
      sizes: HEADSHOT_SIZES,
      image: {
        id: 1,
        name: "author/headshots/original.jpg",
        width: 674,
        height: 800,
      },
      thumbs: [
        {
          id: 1,
          name: "main",
          width: 220,
          height: 180,
          crop_x: 0,
          crop_y: 125,
          crop_w: 674,
          crop_h: 551,
          size: HEADSHOT_SIZES[0]!,
          thumbs: {},
          changed: false,
          url: "/media/main.jpg",
          rendererUrl: THUMBOR_MAIN_1X,
          srcset: THUMBOR_MAIN_SRCSET,
        },
      ],
      cropThumbs: {
        main: {
          id: 1,
          name: "main",
          width: 220,
          height: 180,
          url: "/media/main.jpg",
        },
      },
    });

    expect(model.thumbs.main).toMatchObject({
      url: THUMBOR_MAIN_1X,
      fileUrl: "/media/main.jpg",
      srcset: THUMBOR_MAIN_SRCSET,
    });
  });

  it("opens empty, uploads, crops the one size and completes", () => {
    let model = start({
      sizes: HEADSHOT_SIZES,
      elId: "headshot",
      uploadTo: "author/headshots/%Y/%m",
    });

    expect(model.phase).toBe("upload");
    expect(model.sizes).toHaveLength(1);
    expect(model.crops.main?.box).toBeNull();

    model = run(
      model,
      { type: "fileSelected", selected: true },
      { type: "uploadStarted" },
    );
    expect(model.phase).toBe("uploading");

    model = dialogReducer(model, {
      type: "uploadSucceeded",
      payload: headshotUpload(),
    });

    expect(model.phase).toBe("crop");
    expect(model.fileSelected).toBe(false);
    expect(primarySource(model)).toMatchObject({
      imageId: null,
      name: "author/headshots/{Y}/{m}/{DIR}/original.jpg",
      width: 674,
      height: 800,
      displayUrl: `/media/author/headshots/{Y}/{m}/{DIR}/_preview.jpg${CACHE_BUSTER}`,
    });
    // The box 4.x posted in `thumbs-0-crop_*`.
    expect(model.crops.main?.box).toEqual({ x: 0, y: 125, w: 674, h: 551 });

    model = run(
      model,
      { type: "imageLoaded", width: 421, height: 500 },
      { type: "cropSubmitStarted" },
    );
    expect(model.phase).toBe("saving");

    model = dialogReducer(model, {
      type: "cropSubmitSucceeded",
      payload: headshotCrop(),
    });

    expect(model.phase).toBe("complete");
    expect(model.complete).toBe(true);
    expect(model.thumbs.main).toMatchObject({ id: 1, width: 220, height: 180 });
    expect(model.thumbs.thumb).toMatchObject({ id: 2, name: "thumb" });
    // The saved rendition matches this box, so it is no longer pending.
    expect(model.crops.main?.changed).toBe(false);
  });

  it("stages a replacement without touching crops until the upload lands", () => {
    let model = start({ sizes: HEADSHOT_SIZES, elId: "headshot" });
    model = run(model, {
      type: "uploadSucceeded",
      payload: headshotUpload(),
    });
    const kept = { crops: model.crops, thumbs: model.thumbs };
    const name = primarySource(model).name;

    const replacing = run(
      model,
      { type: "fileSelected", selected: true },
      { type: "beginReplace" },
    );
    expect(replacing.phase).toBe("upload");
    expect(replacing.replacing).toBe(true);
    expect(replacing.fileSelected).toBe(false);
    expect(replacing.crops).toEqual(kept.crops);
    expect(primarySource(replacing).name).toBe(name);

    // Cancel returns to the crop stage with everything as it was.
    const canceled = run(replacing, { type: "cancelReplace" });
    expect(canceled.phase).toBe("crop");
    expect(canceled.replacing).toBe(false);
    expect(canceled.crops).toEqual(kept.crops);
    expect(canceled.thumbs).toEqual(kept.thumbs);

    // A failed upload stays on the replace stage, existing crops intact.
    const failed = run(
      replacing,
      { type: "uploadStarted" },
      { type: "uploadFailed", error: failure("too small") },
    );
    expect(failed.phase).toBe("upload");
    expect(failed.replacing).toBe(true);
    expect(failed.error).toBe("too small");
    expect(failed.crops).toEqual(kept.crops);

    // A successful upload is what resets the crops.
    const replaced = run(
      failed,
      { type: "uploadStarted" },
      { type: "uploadSucceeded", payload: headshotUpload() },
    );
    expect(replaced.phase).toBe("crop");
    expect(replaced.replacing).toBe(false);
    expect(replaced.thumbs).toEqual({});
    expect(replaced.dirty).toBe(true);
  });

  it("only replaces from the crop stage, and only cancels while replacing", () => {
    const empty = start({ sizes: HEADSHOT_SIZES, elId: "headshot" });
    expect(run(empty, { type: "beginReplace" })).toBe(empty);
    expect(run(empty, { type: "cancelReplace" })).toBe(empty);
  });

  it("pairs an uploaded file's object URL with the preview it stands in for", () => {
    let model = start({ sizes: HEADSHOT_SIZES, elId: "headshot" });
    model = run(model, {
      type: "uploadSucceeded",
      payload: headshotUpload(),
      localPreviewUrl: "blob:vitest/0",
    });

    expect(model.localPreview).toEqual({
      url: "blob:vitest/0",
      forDisplayUrl: primarySource(model).displayUrl,
    });

    // A later upload without a stand-in drops the stale one rather than
    // pairing it with a preview of a different file.
    model = run(model, { type: "uploadSucceeded", payload: headshotUpload() });
    expect(model.localPreview).toBeNull();
  });

  it("completes a multi-size save from whichever crop is selected", () => {
    let model = start({
      sizes: LEAD_IMAGE_SIZES,
      image: {
        id: null,
        name: "article/lead_image/{Y}/{m}/{DIR}/original.jpg",
        width: 1300,
        height: 1016,
      },
    });

    expect(model.phase).toBe("crop");
    expect(model.index).toBe(0);
    // Visiting each crop populates it without making an API request.
    expect(model.crops.main?.box).toEqual({ x: 15, y: 0, w: 1270, h: 1016 });
    expect(model.crops.no_height?.box).toBeNull();
    model = dialogReducer(model, { type: "navigateTo", index: 1 });
    expect(model.crops.no_height?.box).not.toBeNull();
    model = dialogReducer(model, { type: "navigateTo", index: 0 });

    model = dialogReducer(model, {
      type: "cropSubmitSucceeded",
      payload: leadImageSuggestion(),
    });

    expect(model.phase).toBe("complete");
    expect(model.index).toBe(0);
    expect(model.complete).toBe(true);
    // Preserve `Size.fit_to_crop()`'s suggestion; `defaultCropBox()` would use
    // the full 1300x1016 frame.
    expect(model.crops.no_height?.box).toEqual({
      x: 15,
      y: 0,
      w: 1270,
      h: 1016,
    });
    // The response's geometry still wins over the client default.
    expect(model.crops.no_height?.changed).toBe(true);
    expect(model.thumbs.main).toMatchObject({ id: 1, width: 600, tmp: true });
  });

  it("knows whether the session differs from what it opened on", () => {
    const image = {
      id: 1,
      name: "article/lead_image/{Y}/{m}/{DIR}/original.jpg",
      width: 1300,
      height: 1016,
    };

    // Every size already has a stored crop: navigating seeds nothing.
    let clean = start({
      sizes: LEAD_IMAGE_SIZES,
      image,
      crops: {
        main: { x: 15, y: 0, w: 1270, h: 1016 },
        no_height: { x: 15, y: 0, w: 1270, h: 1016 },
      },
    });
    expect(clean.dirty).toBe(false);
    clean = run(
      clean,
      { type: "navigateTo", index: 1 },
      { type: "navigateTo", index: 0 },
    );
    expect(clean.dirty).toBe(false);

    // Moving a box is a change.
    const moved = run(
      clean,
      { type: "imageLoaded", width: 650, height: 508 },
      { type: "boxChanged", name: "main", box: { x: 0, y: 0, w: 320, h: 254 } },
    );
    expect(moved.dirty).toBe(true);

    // A size the server has no crop for is seeded when visited, and that
    // seeded box is new state.
    let seeded = start({
      sizes: LEAD_IMAGE_SIZES,
      image,
      crops: { main: { x: 15, y: 0, w: 1270, h: 1016 } },
    });
    expect(seeded.dirty).toBe(false);
    seeded = run(seeded, { type: "navigateTo", index: 1 });
    expect(seeded.dirty).toBe(true);
    // The seed adapts the crop being left behind, exactly as the 4.x crop
    // endpoint's `fit_to_crop` suggestion did.
    expect(seeded.crops.no_height?.box).toEqual({
      x: 15,
      y: 0,
      w: 1270,
      h: 1016,
    });
  });

  it("keeps a flush-edge crop inside the image", () => {
    // The rendered preview is 449.4px tall, but the measured display height
    // is a whole 449: converting a selection dragged flush against the
    // bottom overruns the 1800px image, and `POST api/v1/crop/` rejects a
    // box that extends beyond the image dimensions.
    let model = start({
      sizes: LEAD_IMAGE_SIZES,
      image: { id: 1, name: "unicorn/original.jpg", width: 1440, height: 1800 },
    });
    model = run(
      model,
      { type: "imageLoaded", width: 359, height: 449 },
      {
        type: "boxChanged",
        name: "no_height",
        box: { x: 0, y: 41, w: 359, h: 408.4 },
      },
    );

    const box = model.crops.no_height!.box!;
    // Unclamped, y and h round to 164 and 1637: one pixel past the bottom.
    expect(box).toEqual({ x: 0, y: 163, w: 1440, h: 1637 });
    expect(box.y + box.h).toBeLessThanOrEqual(1800);
  });

  it("keeps renditions already in state when a later payload omits them", () => {
    let model = start({
      sizes: LEAD_IMAGE_SIZES,
      image: {
        id: null,
        name: "article/lead_image/{Y}/{m}/{DIR}/original.jpg",
        width: 1300,
        height: 1016,
      },
    });
    model = dialogReducer(model, {
      type: "cropSubmitSucceeded",
      payload: leadImageSuggestion(),
    });

    // The second response omits main's auto child because main was copied.
    const second = payload({
      image: {
        id: null,
        name: "article/lead_image/{Y}/{m}/{DIR}/original.jpg",
        width: 1300,
        height: 1016,
      },
      sizes: LEAD_IMAGE_SIZES,
      thumbs: {
        main: payloadThumb("main", {
          id: 1,
          width: 600,
          height: 480,
          crop: { x: 15, y: 0, width: 1270, height: 1016 },
          url: "/media/article/lead_image/{Y}/{m}/{DIR}/main_tmp.jpg",
          tmp: true,
        }),
        no_height: payloadThumb("no_height", {
          id: 3,
          width: 600,
          height: 469,
          crop: { x: 15, y: 0, width: 1270, height: 1016 },
          url: "/media/article/lead_image/{Y}/{m}/{DIR}/no_height_tmp.jpg",
          tmp: true,
          changed: true,
        }),
      },
    });
    model = dialogReducer(model, {
      type: "cropSubmitSucceeded",
      payload: second,
    });

    expect(model.phase).toBe("complete");
    // Keep the auto child because `setThumbnails()` rebuilds the select from it.
    expect(Object.keys(model.thumbs).sort()).toEqual([
      "main",
      "no_height",
      "thumb",
    ]);
    expect(model.thumbs.thumb).toMatchObject({ id: 2, ref: "main" });
  });
});

describe("hydrating a modal from the state endpoint", () => {
  const opened = () =>
    start({
      sizes: LEAD_IMAGE_SIZES,
      // Before hydration, the widget knows only the image name.
      image: {
        id: 1,
        name: "article/lead_image/{Y}/{m}/{DIR}/original.jpg",
        width: 0,
        height: 0,
      },
    });

  it("takes the dimensions and the stored boxes it could not know", () => {
    const before = opened();
    expect(primarySource(before).width).toBe(0);
    expect(before.crops.main?.box).toBeNull();

    const model = dialogReducer(before, {
      type: "hydrated",
      payload: leadImageSuggestion({
        image: {
          id: 1,
          name: "article/lead_image/{Y}/{m}/{DIR}/original.jpg",
          width: 1300,
          height: 1016,
        },
      }),
    });

    expect(model.hydrating).toBe(false);
    expect(primarySource(model)).toMatchObject({ width: 1300, height: 1016 });
    expect(model.crops.main?.box).toEqual({ x: 15, y: 0, w: 1270, h: 1016 });
    expect(model.crops.main?.changed).toBe(false);
    expect(model.phase).toBe("crop");
  });

  it("falls back to the upload step when there is no image after all", () => {
    const model = dialogReducer(opened(), {
      type: "hydrated",
      payload: payload({ sizes: LEAD_IMAGE_SIZES }),
    });

    expect(model.phase).toBe("upload");
  });

  it("keeps the dialog usable when the request fails", () => {
    const model = dialogReducer(opened(), {
      type: "hydrateFailed",
      error: failure("You do not have permission to do that."),
    });

    expect(model.hydrating).toBe(false);
    expect(model.error).toBe("You do not have permission to do that.");
  });
});

describe("existing crops", () => {
  it("never recomputes a stored box, however it violates the size", () => {
    const model = start({
      sizes: LEAD_IMAGE_SIZES,
      image: {
        id: 1,
        name: "article/lead_image/{Y}/{m}/{DIR}/original.jpg",
        width: 1300,
        height: 1016,
      },
      crops: { main: { x: 40, y: 30, w: 100, h: 100 } },
      thumbIds: { main: 1 },
    });

    expect(model.crops.main?.box).toEqual({ x: 40, y: 30, w: 100, h: 100 });
    expect(model.thumbs.main).toMatchObject({ id: 1, name: "main" });
  });

  it("keeps a stored box when it is navigated back to", () => {
    let model = start({
      sizes: LEAD_IMAGE_SIZES,
      image: {
        id: 1,
        name: "original.jpg",
        width: 1300,
        height: 1016,
      },
    });
    model = run(model, { type: "navigate", delta: 1 });
    const suggested = model.crops.no_height?.box;
    model = run(
      model,
      { type: "navigate", delta: -1 },
      { type: "navigate", delta: 1 },
    );
    expect(model.crops.no_height?.box).toEqual(suggested);
  });
});

describe("navigation", () => {
  const opened = () =>
    start({
      sizes: LEAD_IMAGE_SIZES,
      image: { id: 1, name: "original.jpg", width: 1300, height: 1016 },
    });

  it("moves within the size list and stops at both ends", () => {
    let model = opened();
    expect(model.index).toBe(0);

    model = run(model, { type: "navigate", delta: -1 });
    expect(model.index).toBe(0);

    model = run(model, { type: "navigate", delta: 1 });
    expect(model.index).toBe(1);
    // Entering a size seeds its box by fitting the crop being left behind.
    expect(model.crops.no_height?.box).toEqual({
      x: 15,
      y: 0,
      w: 1270,
      h: 1016,
    });

    model = run(model, { type: "navigate", delta: 1 });
    expect(model.index).toBe(1);
  });

  it("goes to an index directly, and ignores one out of range", () => {
    let model = run(opened(), { type: "navigateTo", index: 1 });
    expect(model.index).toBe(1);
    model = run(model, { type: "navigateTo", index: 7 });
    expect(model.index).toBe(1);
  });

  it("does not move before there is an image", () => {
    const model = run(start({ sizes: LEAD_IMAGE_SIZES }), {
      type: "navigate",
      delta: 1,
    });
    expect(model.index).toBe(0);
  });
});

describe("dragging a box", () => {
  const cropping = () => {
    let model = start({
      sizes: HEADSHOT_SIZES,
      uploadTo: "author/headshots/%Y/%m",
    });
    model = dialogReducer(model, {
      type: "uploadSucceeded",
      payload: headshotUpload(),
    });
    return dialogReducer(model, {
      type: "imageLoaded",
      width: 421,
      height: 500,
    });
  };

  it("scales the display box into source pixels and rounds once", () => {
    const model = dialogReducer(cropping(), {
      type: "boxChanged",
      name: "main",
      box: { x: 0, y: 78.125, w: 421, h: 344.375 },
    });

    expect(model.crops.main?.box).toEqual({ x: 0, y: 125, w: 674, h: 551 });
    expect(model.crops.main?.changed).toBe(true);
  });

  it("snaps a box that lands one pixel off the size's minimum", () => {
    const scale = 674 / 421;
    const model = dialogReducer(cropping(), {
      type: "boxChanged",
      name: "main",
      box: { x: 0, y: 0, w: 221 / scale, h: 181 / 1.6 },
    });

    expect(model.crops.main?.box).toMatchObject({ w: 220, h: 180 });
  });

  it("ignores a box for a size that is not in the list", () => {
    const model = cropping();
    expect(
      dialogReducer(model, {
        type: "boxChanged",
        name: "nope",
        box: { x: 0, y: 0, w: 10, h: 10 },
      }),
    ).toBe(model);
  });
});

describe("standalone", () => {
  const opened = () =>
    start({ sizes: STANDALONE_SIZES, standalone: true, elId: null });

  it("takes the crop the upload chose, and the sizes with it", () => {
    const model = dialogReducer(opened(), {
      type: "uploadSucceeded",
      payload: standaloneUpload(),
    });

    expect(model.standalone).toBe(true);
    expect(model.sizes).toHaveLength(1);
    expect(model.sizes[0]).toMatchObject({ name: "crop", w: null, h: null });
    expect(model.crops.crop?.box).toEqual({ x: 0, y: 0, w: 674, h: 800 });
    // Upload returns a starting box; `crop/` has not saved a rendition yet.
    expect(model.crops.crop?.changed).toBe(true);
    expect(model.thumbs).toEqual({});
  });

  it("edits the one size, and leaves the crop alone", () => {
    let model = dialogReducer(opened(), {
      type: "uploadSucceeded",
      payload: standaloneUpload(),
    });
    model = dialogReducer(model, {
      type: "standaloneSizeChanged",
      axis: "w",
      value: 300,
    });

    expect(model.sizes[0]).toMatchObject({ w: 300, min_w: 300 });
    expect(model.crops.crop?.box).toEqual({ x: 0, y: 0, w: 674, h: 800 });
    // The rendition on file, if there is one, was made for the old dimensions.
    expect(model.crops.crop?.changed).toBe(true);

    model = dialogReducer(model, {
      type: "standaloneSizeChanged",
      axis: "w",
      value: null,
    });
    expect(model.sizes[0]).toMatchObject({ w: null, min_w: 1 });
  });

  it("completes on the only size, whatever the crop was renamed to", () => {
    let model = dialogReducer(opened(), {
      type: "uploadSucceeded",
      payload: standaloneUpload(),
    });
    model = dialogReducer(model, {
      type: "cropSubmitSucceeded",
      payload: standaloneCrop(),
    });

    expect(model.phase).toBe("complete");
    expect(model.complete).toBe(true);
    expect(model.thumbs["5e4aeac8f"]).toMatchObject({ id: 1, width: 674 });
    // The crop is keyed by the size, the rendition by its own digest.
    expect(model.crops.crop?.box).toEqual({ x: 0, y: 0, w: 674, h: 800 });
  });
});

describe("failures", () => {
  it("shows an upload error and stays on the upload step", () => {
    const model = run(
      start({ sizes: HEADSHOT_SIZES }),
      { type: "fileSelected", selected: true },
      { type: "uploadStarted" },
      { type: "uploadFailed", error: failure("The image is too small.") },
    );

    expect(model.phase).toBe("upload");
    expect(model.error).toBe("The image is too small.");
    expect(model.fileSelected).toBe(false);
  });

  it("keeps a failed standalone upload staged for retry", () => {
    const model = run(
      start({ sizes: HEADSHOT_SIZES, standalone: true }),
      { type: "fileSelected", selected: true },
      { type: "uploadStarted" },
      { type: "uploadFailed", error: failure("The image is too small.") },
    );

    expect(model.phase).toBe("upload");
    expect(model.fileSelected).toBe(true);
  });

  it("shows a crop error and stays on the crop step", () => {
    let model = dialogReducer(start({ sizes: HEADSHOT_SIZES }), {
      type: "uploadSucceeded",
      payload: headshotUpload(),
    });
    model = run(
      model,
      { type: "cropSubmitStarted" },
      { type: "cropSubmitFailed", error: failure("sizes must be a list.") },
    );

    expect(model.phase).toBe("crop");
    expect(model.error).toBe("sizes must be a list.");
    expect(model.crops.main?.box).toEqual({ x: 0, y: 125, w: 674, h: 551 });
  });

  it("keeps the warnings a payload came with", () => {
    const model = dialogReducer(start({ sizes: HEADSHOT_SIZES }), {
      type: "uploadSucceeded",
      payload: headshotUpload({
        warnings: [{ code: "image_small", message: "is a bit small" }],
      }),
    });

    expect(model.warnings).toEqual([
      { code: "image_small", message: "is a bit small" },
    ]);
  });
});

describe("a size with a band rather than a fixed ratio", () => {
  // 600 wide, height free between 400 and 800: ratios 0.75 to 1.5.
  const banded: Size = {
    name: "banded",
    label: "Banded",
    w: 600,
    min_w: 600,
    min_h: 400,
    max_h: 800,
  };

  it("pulls a dragged box back into the band", () => {
    let model = start({
      sizes: [banded],
      image: { id: 1, name: "original.jpg", width: 1000, height: 1000 },
    });
    model = dialogReducer(model, {
      type: "imageLoaded",
      width: 1000,
      height: 1000,
    });

    // The default box for a free-height size is the whole frame.
    expect(model.crops.banded?.box).toEqual({ x: 0, y: 0, w: 1000, h: 1000 });

    // Narrowed to a ratio of 0.3, below the band: the width is the dimension
    // that moved, so the height is derived from the minimum ratio.
    const narrowed = dialogReducer(model, {
      type: "boxChanged",
      name: "banded",
      box: { x: 0, y: 0, w: 300, h: 1000 },
    });
    expect(narrowed.crops.banded?.box).toEqual({ x: 0, y: 0, w: 300, h: 400 });

    // Flattened to 3.33, above it: the height moved, so the width follows.
    const flattened = dialogReducer(model, {
      type: "boxChanged",
      name: "banded",
      box: { x: 0, y: 0, w: 1000, h: 300 },
    });
    expect(flattened.crops.banded?.box).toEqual({ x: 0, y: 0, w: 450, h: 300 });
  });
});

describe("a response whose preview is not what is on screen", () => {
  // The canvas measured the 674x800 upload at 421x500, while the crop response
  // describes an 800x500 preview. Keep using the measured display dimensions.
  const misreported = () =>
    headshotCrop({ preview: { url: null, width: 800, height: 500 } });

  const measured = () => {
    let model = start({
      sizes: HEADSHOT_SIZES,
      uploadTo: "author/headshots/%Y/%m",
    });
    model = dialogReducer(model, {
      type: "uploadSucceeded",
      payload: headshotUpload(),
    });
    return dialogReducer(model, {
      type: "imageLoaded",
      width: 421,
      height: 500,
    });
  };

  it("leaves the dimensions the canvas measured alone", () => {
    const before = primarySource(measured());
    const after = primarySource(
      dialogReducer(measured(), {
        type: "cropSubmitSucceeded",
        payload: misreported(),
      }),
    );

    expect(after.displayWidth).toBe(421);
    expect(after.displayHeight).toBe(500);
    expect(after.displayUrl).toBe(before.displayUrl);
    // Source dimensions still update from the response.
    expect(after.width).toBe(674);
    expect(after.height).toBe(800);
  });

  it("converts a drag that follows it through the measured scale", () => {
    const model = dialogReducer(measured(), {
      type: "cropSubmitSucceeded",
      payload: misreported(),
    });

    const dragged = dialogReducer(model, {
      type: "boxChanged",
      name: "main",
      box: { x: 0, y: 78.125, w: 421, h: 344.375 },
    });

    // 674/421 wide, 800/500 tall. Scaling by the claimed 800x500 instead would
    // put the width at 355.
    expect(dragged.crops.main?.box).toEqual({ x: 0, y: 125, w: 674, h: 551 });
  });
});
