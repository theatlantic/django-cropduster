/**
 * Covers conversions between v1 responses, dialog state, crop requests, and
 * the 4.x completion payload. Comparisons use recorded 4.15 responses.
 */

import { describe, expect, it } from "vitest";

import {
  CACHE_BUSTER,
  HEADSHOT_DIR,
  HEADSHOT_SIZES,
  LEAD_IMAGE_DIR,
  LEAD_IMAGE_SIZES,
  STANDALONE_DIR,
  STANDALONE_SIZES,
  THUMBOR_MAIN_CROP,
  THUMBOR_MAIN_SRCSET,
  THUMBOR_PREVIEW_1X,
  THUMBOR_PREVIEW_SRCSET,
  THUMBOR_SOURCE_HEIGHT,
  THUMBOR_SOURCE_WIDTH,
  headshotCrop,
  headshotUpload,
  leadImageSuggestion,
  payload,
  payloadThumb,
  standaloneCrop,
  thumborHeadshotCrop,
} from "../testing/canonicalFixtures";
import { cropFixture } from "../testing/legacyWire";
import { PRIMARY_SOURCE_ID } from "../state/types";
import {
  canonicalToState,
  stateToCanonicalCropBody,
  stateToLegacyComplete,
  thumbForSize,
} from "./legacyPayload";

describe("canonicalToState", () => {
  it("hangs the original off the primary source", () => {
    const state = canonicalToState(headshotCrop());

    expect(state.sources[PRIMARY_SOURCE_ID]).toEqual({
      id: PRIMARY_SOURCE_ID,
      imageId: null,
      name: `${HEADSHOT_DIR}/original.jpg`,
      url: `/media/${HEADSHOT_DIR}/original.jpg${CACHE_BUSTER}`,
      width: 674,
      height: 800,
      // The canvas uses the renderer URL; the 4.x payload uses the file URL.
      displayUrl: `/media/${HEADSHOT_DIR}/_preview.jpg${CACHE_BUSTER}`,
      displaySrcset: null,
      displayWidth: 421,
      displayHeight: 500,
    });
    expect(state.preview).toEqual({
      url: `/media/${HEADSHOT_DIR}/_preview.jpg${CACHE_BUSTER}`,
      file_url: `/media/${HEADSHOT_DIR}/_preview.jpg`,
      srcset: null,
      width: 421,
      height: 500,
    });
  });

  it("retains renderer density candidates for the canvas and crops", () => {
    const response = thumborHeadshotCrop();

    const state = canonicalToState(response);

    expect(state.sources[PRIMARY_SOURCE_ID]?.displayUrl).toBe(
      THUMBOR_PREVIEW_1X,
    );
    expect(state.sources[PRIMARY_SOURCE_ID]?.displaySrcset).toBe(
      THUMBOR_PREVIEW_SRCSET,
    );
    expect(state.thumbs.main?.srcset).toBe(THUMBOR_MAIN_SRCSET);
    expect(state.thumbs.main?.crop).toEqual(THUMBOR_MAIN_CROP);
  });

  it("keeps every crop, and points each one at the source it came from", () => {
    const state = canonicalToState(headshotCrop());

    expect(Object.keys(state.thumbs).sort()).toEqual(["main", "thumb"]);
    expect(state.thumbs.main).toEqual({
      id: 1,
      name: "main",
      width: 220,
      height: 180,
      url: `/media/${HEADSHOT_DIR}/main_tmp.jpg${CACHE_BUSTER}`,
      fileUrl: `/media/${HEADSHOT_DIR}/main_tmp.jpg`,
      srcset: null,
      crop: { x: 0, y: 125, width: 674, height: 551 },
      ref: null,
      refId: null,
      tmp: true,
      changed: true,
      sourceId: PRIMARY_SOURCE_ID,
    });
    expect(state.thumbs.thumb?.ref).toBe("main");
    expect(state.crops.main).toEqual({
      sourceId: PRIMARY_SOURCE_ID,
      box: { x: 0, y: 125, w: 674, h: 551 },
      changed: false,
    });
  });

  it("marks a box that was suggested but never rendered as pending", () => {
    const state = canonicalToState(leadImageSuggestion());

    expect(state.crops.no_height).toEqual({
      sourceId: PRIMARY_SOURCE_ID,
      box: { x: 15, y: 0, w: 1270, h: 1016 },
      changed: true,
    });
    expect(state.crops.main?.changed).toBe(false);
  });

  it("matches the one standalone crop to the size, whatever it is named", () => {
    const state = canonicalToState(standaloneCrop(), {
      standalone: true,
      sizes: STANDALONE_SIZES,
    });

    expect(Object.keys(state.thumbs)).toEqual(["5e4aeac8f"]);
    expect(state.crops.crop?.box).toEqual({ x: 0, y: 0, w: 674, h: 800 });
  });

  it("tolerates a payload with no image and no crops", () => {
    const state = canonicalToState(payload({ sizes: HEADSHOT_SIZES }));

    expect(state.sources[PRIMARY_SOURCE_ID]?.name).toBe("");
    expect(state.thumbs).toEqual({});
    expect(state.crops.main).toEqual({
      sourceId: PRIMARY_SOURCE_ID,
      box: null,
      changed: false,
    });
  });
});

describe("thumbForSize", () => {
  it("prefers the crop named for the size", () => {
    const state = canonicalToState(headshotCrop());
    expect(thumbForSize(state.thumbs, { name: "main" })?.id).toBe(1);
  });

  it("answers nothing for a size with no crop of its own", () => {
    const state = canonicalToState(headshotCrop());
    expect(thumbForSize(state.thumbs, { name: "no_height" })).toBeNull();
  });

  it("falls back to the one crop that is nobody's rendition, standalone", () => {
    const state = canonicalToState(standaloneCrop());
    expect(
      thumbForSize(state.thumbs, { name: "crop" }, { standalone: true })?.name,
    ).toBe("5e4aeac8f");
  });
});

describe("stateToCanonicalCropBody", () => {
  it("names every declared size, cropped or not", () => {
    const state = canonicalToState(
      payload({
        image: {
          name: `${LEAD_IMAGE_DIR}/original.jpg`,
          width: 1300,
          height: 1016,
        },
        sizes: LEAD_IMAGE_SIZES,
      }),
    );
    const body = stateToCanonicalCropBody(state);

    expect(Object.keys(body.thumbs).sort()).toEqual(["main", "no_height"]);
    expect(body.image).toEqual({
      id: null,
      name: `${LEAD_IMAGE_DIR}/original.jpg`,
      width: 1300,
      height: 1016,
    });
    expect(body.sizes).toBe(state.sizes);
    // A missing crop asks the server to suggest one.
    expect(body.thumbs.no_height).toEqual({
      id: null,
      crop: null,
      width: null,
      height: null,
      changed: false,
      tmp: false,
      source: null,
    });
  });

  it("asks for a render for a first crop, which has no thumb behind it", () => {
    const state = canonicalToState(headshotUpload());
    state.crops.main = {
      sourceId: PRIMARY_SOURCE_ID,
      box: { x: 0, y: 125, w: 674, h: 551 },
      changed: false,
    };

    expect(stateToCanonicalCropBody(state).thumbs.main).toMatchObject({
      id: null,
      crop: { x: 0, y: 125, width: 674, height: 551 },
      changed: true,
    });
  });

  it("asks for nothing when the box is the one the crop was rendered with", () => {
    const state = canonicalToState(headshotCrop());

    expect(stateToCanonicalCropBody(state).thumbs.main).toEqual({
      id: 1,
      crop: { x: 0, y: 125, width: 674, height: 551 },
      width: 220,
      height: 180,
      changed: false,
      // Do not replace this session's temporary rendition with the saved file.
      tmp: true,
      source: null,
    });
  });

  it("asks for a render once the box has moved", () => {
    const state = canonicalToState(headshotCrop());
    state.crops.main = {
      sourceId: PRIMARY_SOURCE_ID,
      box: { x: 10, y: 125, w: 674, h: 551 },
      changed: true,
    };

    expect(stateToCanonicalCropBody(state).thumbs.main).toMatchObject({
      id: 1,
      changed: true,
    });
  });

  it("reserves a source on every crop and names none", () => {
    const state = canonicalToState(headshotCrop());
    for (const entry of Object.values(stateToCanonicalCropBody(state).thumbs)) {
      expect(entry.source).toBeNull();
    }
  });
});

describe("stateToLegacyComplete", () => {
  const recorded = cropFixture("crop_author_headshot").response;

  it("answers what the 4.x crop view answered for the same session", () => {
    const legacy = stateToLegacyComplete(canonicalToState(headshotCrop()));

    expect(legacy.crop.image_id).toBe(recorded.crop.image_id);
    expect(legacy.crop.orig_image).toBe(recorded.crop.orig_image);
    expect(legacy.crop.orig_w).toBe(recorded.crop.orig_w);
    expect(legacy.crop.orig_h).toBe(recorded.crop.orig_h);
    expect(legacy.crop.standalone).toBe(recorded.crop.standalone);
    // `setThumbnails()` rebuilds the select from this map, including auto children.
    expect(legacy.crop.thumbs).toEqual(recorded.crop.thumbs);
    expect(legacy.initial).toBe(true);
    expect(legacy.preview_url).toBe(recorded.preview_url);
    expect(legacy.preview_w).toBe(recorded.preview_w);
    expect(legacy.preview_h).toBe(recorded.preview_h);
  });

  it("echoes one entry per size, as the crop formset did", () => {
    const legacy = stateToLegacyComplete(canonicalToState(headshotCrop()));
    const [entry, ...rest] = legacy.thumbs;
    const [expected] = recorded.thumbs;

    expect(rest).toEqual([]);
    for (const field of [
      "id",
      "name",
      "width",
      "height",
      "crop_x",
      "crop_y",
      "crop_w",
      "crop_h",
      "changed",
      "url",
    ] as const) {
      expect([field, entry?.[field]]).toEqual([field, expected?.[field]]);
    }
    // The auto child belongs to its parent size, not this rendition map.
    expect(entry?.thumbs).toEqual(expected?.thumbs);
    expect(entry?.size).toEqual(HEADSHOT_SIZES[0]);
  });

  it("reports a crop's file twice: temporary now, permanent once saved", () => {
    const legacy = stateToLegacyComplete(canonicalToState(headshotCrop()));

    expect(legacy.crop.thumbs.main?.url).toBe(
      `/media/${HEADSHOT_DIR}/main_tmp.jpg`,
    );
    expect(legacy.thumbs[0]?.url).toBe(`/media/${HEADSHOT_DIR}/main.jpg`);
  });

  /**
   * CKEditor persists `thumbs[0].url`, so the 4.x completion payload must use
   * storage file URLs rather than renderer URLs.
   */
  it("reports files rather than the renderer's URLs", () => {
    const payload = headshotCrop();
    const legacy = stateToLegacyComplete(canonicalToState(payload));

    // Confirm the v1 response uses a cache-busted renderer URL.
    expect(payload.thumbs.main?.url).toContain("?mod=");
    for (const url of [
      legacy.crop.thumbs.main?.url,
      legacy.crop.thumbs.thumb?.url,
      legacy.thumbs[0]?.url,
      legacy.thumbs[0]?.thumbs?.main?.url,
      legacy.preview_url,
    ]) {
      expect(url).not.toContain("?");
    }
  });

  /**
   * Use `preview.file_url` when the renderer uses another host, matching the
   * storage URL rendered into `data-preview-url`.
   */
  it("reports the preview's file when the renderer answers on another host", () => {
    const state = canonicalToState(
      headshotCrop({
        image: {
          width: THUMBOR_SOURCE_WIDTH,
          height: THUMBOR_SOURCE_HEIGHT,
        },
        preview: {
          url: `https://thumbor.example.com/CsdSvckjMNUU=/fit-in/800x500/media/${HEADSHOT_DIR}/original.jpg`,
          srcset: THUMBOR_PREVIEW_SRCSET,
          file_url: `/media/${HEADSHOT_DIR}/_preview.jpg`,
          width: 421,
          height: 500,
        },
      }),
    );
    const legacy = stateToLegacyComplete(state);

    expect(legacy.preview_url).toBe(`/media/${HEADSHOT_DIR}/_preview.jpg`);
    // The canvas continues to use the renderer URL.
    expect(state.sources[PRIMARY_SOURCE_ID]?.displayUrl).toContain(
      "thumbor.example.com",
    );
    expect(state.sources[PRIMARY_SOURCE_ID]?.displaySrcset).toBe(
      THUMBOR_PREVIEW_SRCSET,
    );
  });

  it("falls back to stripping the query for a server with no file_url", () => {
    const state = canonicalToState(
      headshotCrop({
        preview: {
          url: `/media/${HEADSHOT_DIR}/_preview.jpg${CACHE_BUSTER}`,
          width: 421,
          height: 500,
        },
        thumbs: {
          main: payloadThumb("main", {
            id: 1,
            width: 220,
            height: 180,
            crop: { x: 0, y: 125, width: 674, height: 551 },
            url: `/media/${HEADSHOT_DIR}/main_tmp.jpg`,
            fileUrl: null,
            tmp: true,
          }),
        },
      }),
    );
    const legacy = stateToLegacyComplete(state);

    expect(legacy.crop.thumbs.main?.url).toBe(
      `/media/${HEADSHOT_DIR}/main_tmp.jpg`,
    );
    expect(legacy.thumbs[0]?.url).toBe(`/media/${HEADSHOT_DIR}/main.jpg`);
    expect(legacy.preview_url).toBe(`/media/${HEADSHOT_DIR}/_preview.jpg`);
  });

  it("fills the sizes 4.x reported as null", () => {
    const legacy = stateToLegacyComplete(canonicalToState(headshotCrop()));

    // 4.x returned `crop.sizes` as null; 5.0 fills it from dialog state.
    expect(recorded.crop.sizes).toBeNull();
    expect(legacy.crop.sizes).toEqual(HEADSHOT_SIZES);
  });

  it("leaves a suggested crop with no file and no pk", () => {
    const legacy = stateToLegacyComplete(
      canonicalToState(leadImageSuggestion()),
    );
    const suggested = cropFixture("crop_lead_image_suggest").response.thumbs[1];

    expect(legacy.thumbs[1]).toMatchObject({
      id: suggested?.id ?? null,
      name: "no_height",
      crop_x: suggested?.crop_x,
      crop_y: suggested?.crop_y,
      crop_w: suggested?.crop_w,
      crop_h: suggested?.crop_h,
      thumbs: {},
    });
    expect(legacy.thumbs[1]).not.toHaveProperty("url");
    expect(legacy.crop.thumbs).not.toHaveProperty("no_height");

    // A crop without a file has null dimensions, as in 4.x.
    expect(suggested?.width).toBeNull();
    expect(legacy.thumbs[1]?.width).toBeNull();
    expect(legacy.thumbs[1]?.height).toBeNull();
  });

  it("answers a standalone crop with the entry CKEditor reads", () => {
    const state = canonicalToState(standaloneCrop(), {
      standalone: true,
      sizes: STANDALONE_SIZES,
    });
    const legacy = stateToLegacyComplete(state);
    const expected = cropFixture("standalone_crop").response;

    expect(legacy.crop.thumbs).toEqual(expected.crop.thumbs);
    // CKEditor reads these fields from `thumbs[0]`.
    expect(legacy.thumbs[0]).toMatchObject({
      width: 674,
      height: 800,
      url: `/media/${STANDALONE_DIR}/5e4aeac8f.jpg`,
    });
  });

  it("emits an empty crop for state with no source yet", () => {
    const legacy = stateToLegacyComplete(
      canonicalToState(payload({ sizes: [] })),
    );

    expect(legacy.crop).toMatchObject({
      image_id: null,
      orig_image: "",
      orig_w: 0,
      orig_h: 0,
      thumbs: {},
    });
    expect(legacy.thumbs).toEqual([]);
    expect(legacy.preview_url).toBe("");
  });
});

/**
 * Matches `_legacy_preview_size()`, including its 800x500 result for originals
 * that fit inside the preview box.
 */
describe("the preview dimensions the legacy payload reports", () => {
  const cases: [number | null, number | null, number, number, string][] = [
    [700, 500, 800, 500, "an original that fits inside the box"],
    [800, 500, 800, 500, "an original exactly the size of the box"],
    [1600, 1000, 800, 500, "an original scaled by a whole ratio"],
    [1300, 1016, 640, 500, "the recorded lead_image original"],
    [674, 800, 421, 500, "the recorded headshot original"],
    [null, null, 800, 500, "an image whose dimensions are not known"],
    [700, 0, 800, 500, "an image with one dimension missing"],
  ];

  for (const [width, height, w, h, name] of cases) {
    it(`reports ${w}x${h} for ${name}`, () => {
      const legacy = stateToLegacyComplete(
        canonicalToState(payload({ image: { width, height } })),
      );

      expect([legacy.preview_w, legacy.preview_h]).toEqual([w, h]);
    });
  }

  it("agrees with the preview the server reported for a scaled original", () => {
    // Only originals inside the preview box differ from its dimensions.
    const scaled = leadImageSuggestion();
    const legacy = stateToLegacyComplete(canonicalToState(scaled));

    expect([legacy.preview_w, legacy.preview_h]).toEqual([
      scaled.preview?.width,
      scaled.preview?.height,
    ]);
  });
});
