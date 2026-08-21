/**
 * Golden default-crop vectors extracted from the unmodified 4.x dialog JS.
 *
 * Run: node tests/legacy/extract-vectors.mjs   (from frontend/)
 * Writes: frontend/tests/golden/default-crop-vectors.json
 *
 * What is being captured, and why it is the same code path the dialog uses:
 *
 *   A fresh upload is handled by `CropBoxClass.onSuccess`, which sets `orig_w`/
 *   `orig_h` from the server's crop data, points `#cropbox` at the uploaded
 *   image, and polls until it loads. `onImageLoad` then does exactly:
 *
 *       this.index = 0;
 *       var sizeData = $.parseJSON($('#id_thumbs-0-size').val() || '{}');
 *       this.setCropOptions(sizeData);
 *
 *   `setCropOptions` computes the aspect ratio and extent, calls
 *   `getCropSelect(aspectRatio, aspectExtent)` to build Jcrop's `setSelect`,
 *   and `getCropSelect` in turn calls `updateCoordinates`, which writes
 *   `#id_thumbs-0-crop_{x,y,w,h}` (the values POSTed to the
 *   crop view and stored on Thumb). Each vector calls `setCropOptions(size)`
 *   on a fresh CropBoxClass and records both the returned
 *   `setSelect` box and the values that landed in the hidden inputs.
 *
 * Details that the port must preserve, and where they show up in the vectors:
 *
 *   - `getAspectRatioExtent` returns `max: Infinity` for a size with no fixed
 *     aspect and no capping max_w/max_h; `setCropOptions` then coerces that
 *     Infinity to 0 before handing the extent to `getCropSelect`, where 0 means
 *     "no constraint". Recorded as `aspectExtentRaw` (pre-coercion, Infinity
 *     serialized as the string "Infinity") vs `aspectExtent` (what
 *     `getCropSelect` actually sees).
 *   - `min_w`/`min_h` only widen the aspect band when > 1 (a min of exactly 1
 *     is the "no minimum" sentinel), while `calcMinSize` treats them as plain
 *     minimums. Recorded as `aspectExtent` vs `minSize`.
 *   - Jcrop's `minSize` comes from `calcMinSize(size)`, which widens for
 *     *required* autos only. `setCropOptions` separately computes a local
 *     `minSize` object widened by *all* autos and then never uses it; the
 *     mirror of that dead value is recorded as `deadLocalMinSize` so a port can
 *     prove the branch is dead (it differs from `minSize` only for size sets
 *     with an optional auto larger than the parent, e.g. OptionalSizes).
 *   - Every placement uses JS `Math.round` (half-up, and `Math.round(-0.5)` is
 *     -0), so the source dimensions below deliberately include `.5` boundaries.
 *   - An existing stored crop is returned untouched and does not write the
 *     hidden inputs (recomputing it would silently re-center saved crops).
 *     Covered in `edgeCases`.
 */

/* global console, process */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import {
  GOLDEN_DIR,
  createLegacyEnv,
  generatedFromLabel,
  installJcropStub,
  jsonNumber,
  setNaturalSize,
  writeGoldenJson,
} from "./legacy-env.mjs";

/**
 * The first eleven are a fixed list (674x800 is the test suite's
 * source image, the rest cover square/extreme/portrait/landscape and off-by-one
 * dimensions). The last three are chosen so that both `Math.round` calls in
 * `getCropSelect` fall on a `.5` boundary for the three aspect ratios the test
 * app's size sets use: 2 (Article.ALT wide 600x300), 1.25 (Article.LEAD /
 * MultipleFields / OptionalSizes / OrphanedThumbs main 600x480) and 11/9
 * (Author.HEADSHOT main 220x180):
 *
 *   1001x1200 (portrait, taller than all three ratios)
 *     aspect 2:    h = round(1001/2)      = round(500.5) = 501,
 *                  y = round((1200-501)/2) = round(349.5) = 350
 *     aspect 1.25: y = round((1200-801)/2) = round(199.5) = 200
 *     aspect 11/9: y = round((1200-819)/2) = round(190.5) = 191
 *   1001x502 (landscape; straddles the branch: taller than 2, wider than the
 *   other two)
 *     aspect 2:    h = round(500.5) = 501, y = round((502-501)/2) = round(0.5) = 1
 *     aspect 1.25: w = round(502*1.25)  = round(627.5) = 628,
 *                  x = round((1001-628)/2) = round(186.5) = 187
 *     aspect 11/9: x = round((1001-614)/2) = round(193.5) = 194
 *   675x801 (portrait)
 *     aspect 2:    h = round(337.5) = 338, y = round((801-338)/2) = round(231.5) = 232
 *     aspect 1.25: y = round((801-540)/2) = round(130.5) = 131
 *     aspect 11/9: y = round((801-552)/2) = round(124.5) = 125
 */
const SOURCE_DIMS = [
  [674, 800],
  [1300, 1016],
  [1, 1],
  [3000, 100],
  [100, 3000],
  [1920, 1080],
  [1080, 1920],
  [1000, 1000],
  [801, 600],
  [599, 601],
  [1201, 961],
  [1001, 1200],
  [1001, 502],
  [675, 801],
];

const HTML = `
  <img id="cropbox" src="data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw==">
  <input type="checkbox" id="id_standalone">
  <input type="hidden" id="id_crop-sizes" value="[]">
  <input type="hidden" id="id_crop-orig_w" value="">
  <input type="hidden" id="id_crop-orig_h" value="">
  <input type="hidden" id="id_thumbs-0-size" value="">
  <input type="hidden" id="id_thumbs-0-crop_x" value="">
  <input type="hidden" id="id_thumbs-0-crop_y" value="">
  <input type="hidden" id="id_thumbs-0-crop_w" value="">
  <input type="hidden" id="id_thumbs-0-crop_h" value="">
  <div class="cropduster-thumb-form"></div>
`;

const CROP_FIELDS = ["crop_x", "crop_y", "crop_w", "crop_h"];
const UNTOUCHED = "__untouched__";

const { window, $, legacy } = createLegacyEnv(HTML);
const jcrop = installJcropStub($);
const cropboxImg = window.document.getElementById("cropbox");

function setThumbInputs(value) {
  CROP_FIELDS.forEach((field) => $(`#id_thumbs-0-${field}`).val(value));
}

function readThumbInputs() {
  const raw = {};
  CROP_FIELDS.forEach((field) => {
    raw[field] = $(`#id_thumbs-0-${field}`).val();
  });
  return raw;
}

function readSelect() {
  const raw = readThumbInputs();
  return {
    x: Number(raw.crop_x),
    y: Number(raw.crop_y),
    w: Number(raw.crop_w),
    h: Number(raw.crop_h),
  };
}

/**
 * Mirror of the local `minSize` object `setCropOptions` builds and discards:
 * `calcMinSize` without the `required` filter on autos. Not captured from the
 * running code (it is a local with no observable effect); recomputed here so a
 * port can assert the dead branch stays dead.
 */
function deadLocalMinSize(size) {
  let w = size.min_w || size.w || 0;
  let h = size.min_h || size.h || 0;
  for (const auto of size.auto || []) {
    w = Math.max(w, auto.min_w || auto.w || 0);
    h = Math.max(h, auto.min_h || auto.h || 0);
  }
  return [w, h];
}

/** Run one size/source pair through the same call used by `onImageLoad()`. */
function extract(size, origW, origH, { existingThumb = null } = {}) {
  const cropBox = new legacy.CropBoxClass();
  cropBox.orig_w = origW;
  cropBox.orig_h = origH;
  cropBox.index = 0;
  // After a fresh upload `this.data` is the merge of the server response with
  // getFormData(), whose `thumbs` is always an array with one (zero-filled)
  // entry per rendered thumb form.
  cropBox.data = {
    thumbs: [existingThumb || { crop_x: 0, crop_y: 0, crop_w: 0, crop_h: 0 }],
  };

  setNaturalSize(cropboxImg, origW, origH);
  setThumbInputs(existingThumb ? UNTOUCHED : "");
  jcrop.reset();

  const rawExtent = cropBox.getAspectRatioExtent(size);
  cropBox.setCropOptions(size);
  const options = jcrop.last();
  if (!options) {
    throw new Error("setCropOptions did not reach Jcrop");
  }

  return {
    cropBox,
    options,
    rawExtent,
    vector: {
      input: {
        origW,
        origH,
        size,
      },
      select: readSelect(),
      setSelect: options.setSelect,
      minSize: options.minSize,
      deadLocalMinSize: deadLocalMinSize(size),
      aspectRatio: "aspectRatio" in options ? options.aspectRatio : 0,
      aspectExtent: {
        min: jsonNumber(
          "aspectRatio" in options ? rawExtent.min : options.minAspectRatio,
        ),
        max: jsonNumber(
          "aspectRatio" in options
            ? rawExtent.max === Infinity
              ? 0
              : rawExtent.max
            : options.maxAspectRatio,
        ),
      },
      aspectExtentRaw: {
        min: jsonNumber(rawExtent.min),
        max: jsonNumber(rawExtent.max),
      },
      trueSize: options.trueSize,
      boxSize: [options.boxWidth, options.boxHeight],
    },
  };
}

const sizeSets = [];
const testSizes = JSON.parse(
  readFileSync(resolve(GOLDEN_DIR, "test-sizes.json"), "utf8"),
);
for (const set of Object.keys(testSizes).sort()) {
  sizeSets.push({ source: "test", set, sizes: testSizes[set] });
}
const sampleSizes = JSON.parse(
  readFileSync(resolve(GOLDEN_DIR, "sample-sizes.json"), "utf8"),
);
for (const set of Object.keys(sampleSizes).sort()) {
  const entry = sampleSizes[set];
  if (!entry || !Array.isArray(entry.sizes) || !entry.sizes.length) continue;
  sizeSets.push({
    source: "sample",
    set,
    sizes: entry.sizes,
    fieldIdentifier: entry.field_identifier,
  });
}

const vectors = [];
for (const { source, set, sizes } of sizeSets) {
  sizes.forEach((size, sizeIndex) => {
    for (const [origW, origH] of SOURCE_DIMS) {
      const { vector } = extract(size, origW, origH);
      vector.input = {
        source,
        set,
        sizeIndex,
        sizeName: size.name,
        origW,
        origH,
        size,
      };
      vectors.push(vector);
    }
  });
}

// ---------------------------------------------------------------------------
// Edge cases: the existing-crop passthrough and updateCoordinates' clamp/snap.
// ---------------------------------------------------------------------------

const edgeCases = [];
const headshotMain = testSizes["Author.HEADSHOT_SIZES"][0];

for (const [label, stored] of [
  [
    "existing crop, aspect-consistent",
    { crop_x: 13, crop_y: 27, crop_w: 400, crop_h: 327 },
  ],
  [
    "existing crop, violates the size aspect ratio",
    { crop_x: 100, crop_y: 200, crop_w: 500, crop_h: 100 },
  ],
  [
    "existing crop, string values as read back from the form",
    { crop_x: "5", crop_y: "6", crop_w: "660", crop_h: "540" },
  ],
]) {
  const { vector } = extract(headshotMain, 674, 800, { existingThumb: stored });
  edgeCases.push({
    kind: "existing-crop-passthrough",
    label,
    input: {
      source: "test",
      set: "Author.HEADSHOT_SIZES",
      sizeIndex: 0,
      sizeName: headshotMain.name,
      origW: 674,
      origH: 800,
      size: headshotMain,
      existingThumb: stored,
      thumbInputsBefore: UNTOUCHED,
    },
    setSelect: vector.setSelect,
    minSize: vector.minSize,
    // Unchanged from `thumbInputsBefore`: getCropSelect returns early without
    // calling updateCoordinates.
    thumbInputsAfter: readThumbInputs(),
  });
}

for (const [label, coords, jcropOptions] of [
  [
    "no jcrop instance yet, integral box",
    { x: 10, y: 20, w: 300, h: 400 },
    null,
  ],
  [
    "negative x and y are clamped by shrinking w and h",
    { x: -10, y: -20, w: 300, h: 400 },
    null,
  ],
  [
    "fractional coordinates round half up",
    { x: 10.5, y: 10.5, w: 100.5, h: 99.5 },
    null,
  ],
  [
    "Math.round(-0.5) is -0, so no negative clamp fires",
    { x: -0.5, y: -0.5, w: 100.4, h: 100.6 },
    null,
  ],
  [
    "x rounds to a negative before clamping",
    { x: -0.6, y: -1.4, w: 100, h: 100 },
    null,
  ],
  [
    "w one under minSize snaps up",
    { x: 0, y: 0, w: 219, h: 181 },
    { minSize: [220, 180] },
  ],
  [
    "w two under minSize does not snap",
    { x: 0, y: 0, w: 218, h: 178 },
    { minSize: [220, 180] },
  ],
  [
    "negative clamp first, then minSize snap",
    { x: -1, y: 0, w: 222, h: 180 },
    { minSize: [220, 180] },
  ],
  [
    "w one over maxSize snaps down",
    { x: 0, y: 0, w: 601, h: 399 },
    { maxSize: [600, 400] },
  ],
  [
    "minSize and maxSize both present",
    { x: 0, y: 0, w: 221, h: 401 },
    { minSize: [220, 180], maxSize: [600, 400] },
  ],
]) {
  const cropBox = new legacy.CropBoxClass();
  cropBox.index = 0;
  if (jcropOptions) {
    cropBox.jcrop = { getOptions: () => jcropOptions };
  }
  setThumbInputs("");
  cropBox.updateCoordinates(coords, 0);
  edgeCases.push({
    kind: "update-coordinates",
    label,
    input: { coords, jcropOptions },
    select: readSelect(),
  });
}

// ---------------------------------------------------------------------------
// Self-check. The 674x800 / Author.HEADSHOT_SIZES "main" box is asserted by
// tests/test_admin.py::test_addform (crop_x 0, crop_y 125, crop_w 674,
// crop_h 551); Math.round(124.5) == 125.
// ---------------------------------------------------------------------------

function selfCheck() {
  const failures = [];
  const vector = vectors.find(
    (v) =>
      v.input.source === "test" &&
      v.input.set === "Author.HEADSHOT_SIZES" &&
      v.input.sizeName === "main" &&
      v.input.origW === 674 &&
      v.input.origH === 800,
  );
  if (!vector) {
    failures.push("no vector for test/Author.HEADSHOT_SIZES/main at 674x800");
  } else {
    const expected = { x: 0, y: 125, w: 674, h: 551 };
    if (JSON.stringify(vector.select) !== JSON.stringify(expected)) {
      failures.push(
        `select ${JSON.stringify(vector.select)} != ${JSON.stringify(expected)} (tests/test_admin.py)`,
      );
    }
    if (
      JSON.stringify(vector.setSelect) !== JSON.stringify([0, 125, 674, 676])
    ) {
      failures.push(
        `setSelect ${JSON.stringify(vector.setSelect)} != [0,125,674,676]`,
      );
    }
    // Size('main', 220, 180) with a required auto Size('thumb', 110, 90):
    // calcMinSize maxes the parent minimum against the required auto, which is
    // smaller here, so the widening is a no-op and minSize stays [220, 180].
    if (JSON.stringify(vector.minSize) !== JSON.stringify([220, 180])) {
      failures.push(`minSize ${JSON.stringify(vector.minSize)} != [220,180]`);
    }
    if (
      JSON.stringify(vector.deadLocalMinSize) !== JSON.stringify([220, 180])
    ) {
      failures.push(
        `deadLocalMinSize ${JSON.stringify(vector.deadLocalMinSize)} != [220,180]`,
      );
    }
  }

  // The optional (required=false) auto is 1200x960: calcMinSize skips it, the
  // dead local in setCropOptions would not have.
  const optional = vectors.find(
    (v) =>
      v.input.set === "OptionalSizes.TEST_SIZES" &&
      v.input.origW === 674 &&
      v.input.origH === 800,
  );
  if (!optional) {
    failures.push("no vector for OptionalSizes.TEST_SIZES at 674x800");
  } else if (
    JSON.stringify(optional.minSize) !== JSON.stringify([600, 480]) ||
    JSON.stringify(optional.deadLocalMinSize) !== JSON.stringify([1200, 960])
  ) {
    failures.push(
      `OptionalSizes minSize/deadLocalMinSize ${JSON.stringify(optional.minSize)}/` +
        `${JSON.stringify(optional.deadLocalMinSize)} != [600,480]/[1200,960]`,
    );
  }

  const passthrough = edgeCases.find(
    (c) => c.kind === "existing-crop-passthrough",
  );
  if (
    JSON.stringify(passthrough.setSelect) !== JSON.stringify([13, 27, 413, 354])
  ) {
    failures.push(
      `passthrough setSelect ${JSON.stringify(passthrough.setSelect)} != [13,27,413,354]`,
    );
  }
  if (
    Object.values(passthrough.thumbInputsAfter).some((v) => v !== UNTOUCHED)
  ) {
    failures.push(
      `passthrough wrote the hidden inputs: ${JSON.stringify(passthrough.thumbInputsAfter)}`,
    );
  }

  if (failures.length) {
    console.error("SELF-CHECK FAILED:");
    failures.forEach((f) => console.error(`  - ${f}`));
    process.exit(1);
  }
}

selfCheck();

writeGoldenJson(
  resolve(GOLDEN_DIR, "default-crop-vectors.json"),
  {
    generatedFrom: generatedFromLabel(),
    generatedBy: "frontend/tests/legacy/extract-vectors.mjs",
    description:
      "Default crop boxes computed by the unmodified 4.x dialog (CropBoxClass.setCropOptions -> " +
      "getCropSelect -> updateCoordinates) for a fresh upload with no stored crop. `select` " +
      "was written to #id_thumbs-0-crop_{x,y,w,h}; `setSelect` is the [x0,y0,x1,y1] box passed to Jcrop. " +
      "`aspectExtentRaw` is getAspectRatioExtent output (Infinity as a string); `aspectExtent` is what " +
      "getCropSelect saw after setCropOptions coerced Infinity to 0. `minSize` is calcMinSize(size) " +
      "(required autos only); `deadLocalMinSize` mirrors the all-autos local that setCropOptions " +
      "computes and never uses.",
    sourceDims: SOURCE_DIMS,
    counts: {
      sizeSets: sizeSets.length,
      sizes: sizeSets.reduce((n, s) => n + s.sizes.length, 0),
      sourceDims: SOURCE_DIMS.length,
      vectors: vectors.length,
      edgeCases: edgeCases.length,
    },
    vectors,
    edgeCases,
  },
  ["vectors", "edgeCases"],
);

console.log(
  `default-crop-vectors.json: ${vectors.length} vectors + ${edgeCases.length} edge cases ` +
    `(${sizeSets.length} size sets, ${SOURCE_DIMS.length} source dims); self-check OK`,
);
