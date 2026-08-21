/**
 * Golden vectors for `syncSizeForm` in the unmodified 4.x dialog JS.
 *
 * Run: node tests/legacy/extract-sizeform-vectors.mjs   (from frontend/)
 * Writes: frontend/tests/golden/size-form-vectors.json
 *
 * `syncSizeForm` runs only in the standalone dialog (`#id_standalone`
 * checked), on every `updateCoordinates` and after every upload/crop response.
 * It mirrors the single size in `#id_crop-sizes` into the `#id_size-width` /
 * `#id_size-height` inputs, reveals the width/height rows once a crop exists,
 * and computes the *placeholder* the editor sees for whichever dimension they
 * left blank.
 *
 * Branches covered by the grid below, and the quirks in each:
 *
 *   - Not standalone: returns before touching anything (the pre-state below
 *     survives verbatim).
 *   - `#id_crop-sizes` not a one-element array (empty, two sizes, `null`,
 *     unparseable): both inputs are *already blanked* by the time the guard
 *     returns, but placeholders are left alone.
 *   - Size inputs missing from the DOM: returns before the rows are shown.
 *   - `size.max_w`/`max_h` clamp via `Math.min(max, <string from .val()>)`, so
 *     a blank input becomes the number 0 and a populated one becomes a number.
 *   - Width known, height blank: the height placeholder is scaled from
 *     `sizes[0].w`, the *uncapped* size width, not the max_w-clamped
 *     `userWidth` computed two lines earlier.
 *   - Neither known: two mutually exclusive rescales of the crop box, and the
 *     condition selecting between them parses as
 *     `(crop_w && crop_h && (max_w && crop_w > max_w)) || (max_h && crop_h > max_h)`,
 *     so a missing crop_w with an over-max crop_h still enters the first branch
 *     and propagates NaN into the width placeholder (which then gets removed).
 *     The first branch scales by the *largest* applicable ratio and then clamps;
 *     the second scales by the *smallest* ratio, relative to the original image
 *     rather than the crop.
 *   - All placement uses JS `Math.round` (half-up).
 */

/* global console, process */

import { resolve } from "node:path";

import {
  GOLDEN_DIR,
  createLegacyEnv,
  generatedFromLabel,
  writeGoldenJson,
} from "./legacy-env.mjs";

const HTML = `
  <input type="checkbox" id="id_standalone">
  <input type="hidden" id="id_crop-sizes" value="[]">
  <input type="hidden" id="id_crop-orig_w" value="">
  <input type="hidden" id="id_crop-orig_h" value="">
  <input type="hidden" id="id_thumbs-0-crop_w" value="">
  <input type="hidden" id="id_thumbs-0-crop_h" value="">
  <form id="size">
    <div class="row width" style="display: none;">
      <input type="text" id="id_size-width" name="size-width">
    </div>
    <div class="row height" style="display: none;">
      <input type="text" id="id_size-height" name="size-height">
    </div>
  </form>
`;

/** Sentinels so that "left alone" and "set to empty" are distinguishable. */
const PRE_STATE = {
  widthValue: "PRE-W",
  heightValue: "PRE-H",
  widthPlaceholder: "PRE-PW",
  heightPlaceholder: "PRE-PH",
  rowDisplay: "none",
};

function size(props) {
  return {
    __type__: "Size",
    name: "standalone",
    label: "Standalone",
    w: null,
    h: null,
    min_w: null,
    min_h: null,
    max_w: null,
    max_h: null,
    retina: 0,
    required: true,
    ...props,
  };
}

const SIZES = [
  ["w+h", size({ w: 600, h: 480 })],
  ["w only", size({ w: 600, h: null })],
  ["h only", size({ w: null, h: 480 })],
  ["free", size({ w: null, h: null })],
  ["w+h, max_w below w", size({ w: 600, h: 480, max_w: 300 })],
  ["w only, max_w below w", size({ w: 600, h: null, max_w: 300 })],
  ["h only, max_h below h", size({ w: null, h: 480, max_h: 240 })],
  ["free, max_w", size({ w: null, h: null, max_w: 1200 })],
  ["free, max_h", size({ w: null, h: null, max_h: 900 })],
  ["free, max_w+max_h", size({ w: null, h: null, max_w: 1200, max_h: 900 })],
];

/**
 * [orig_w, orig_h, crop_w, crop_h] as they appear in the hidden inputs ('' = the
 * field is blank, which parseInt turns into NaN).
 *
 * The 1600x1204 crop makes the width-known placeholder fall on a .5 boundary:
 * round((600 / 1600) * 1204) == round(451.5) == 452.
 */
const DIMS = [
  ["orig 2000x1500, crop 1600x1200", [2000, 1500, 1600, 1200]],
  ["orig 2001x1501, crop 1600x1204", [2001, 1501, 1600, 1204]],
  ["orig 3000x2000, crop 3000x2000", [3000, 2000, 3000, 2000]],
  ["orig 2000x1500, crop 800x600", [2000, 1500, 800, 600]],
  ["orig 2000x1500, no crop", [2000, 1500, "", ""]],
  ["no orig, crop 800x600", ["", "", 800, 600]],
  ["orig 2000x1500, crop_w blank, crop_h 1200", [2000, 1500, "", 1200]],
];

const { window, $, legacy } = createLegacyEnv(HTML);
const document = window.document;

function resetForm() {
  $("#id_size-width")
    .val(PRE_STATE.widthValue)
    .attr("placeholder", PRE_STATE.widthPlaceholder);
  $("#id_size-height")
    .val(PRE_STATE.heightValue)
    .attr("placeholder", PRE_STATE.heightPlaceholder);
  document.querySelector(".row.width").style.display = PRE_STATE.rowDisplay;
  document.querySelector(".row.height").style.display = PRE_STATE.rowDisplay;
}

function attr(selector, name) {
  const value = $(selector).attr(name);
  return value === undefined ? null : value;
}

function readForm() {
  const widthRow = document.querySelector(".row.width");
  const heightRow = document.querySelector(".row.height");
  return {
    widthValue: $("#id_size-width").length ? $("#id_size-width").val() : null,
    heightValue: $("#id_size-height").length
      ? $("#id_size-height").val()
      : null,
    widthPlaceholder: $("#id_size-width").length
      ? attr("#id_size-width", "placeholder")
      : null,
    heightPlaceholder: $("#id_size-height").length
      ? attr("#id_size-height", "placeholder")
      : null,
    rowWidthDisplay: widthRow.style.display,
    rowHeightDisplay: heightRow.style.display,
    rowsShown: widthRow.style.display !== "none",
  };
}

/**
 * @param {object} state {standalone, cropSizesRaw, orig_w, orig_h, crop_w, crop_h}
 */
function run(state) {
  resetForm();
  $("#id_standalone").prop("checked", !!state.standalone);
  $("#id_crop-sizes").val(state.cropSizesRaw);
  $("#id_crop-orig_w").val(String(state.orig_w));
  $("#id_crop-orig_h").val(String(state.orig_h));
  $("#id_thumbs-0-crop_w").val(String(state.crop_w));
  $("#id_thumbs-0-crop_h").val(String(state.crop_h));
  legacy.syncSizeForm();
  return readForm();
}

const vectors = [];

for (const [sizeLabel, sizeObj] of SIZES) {
  for (const [dimLabel, [orig_w, orig_h, crop_w, crop_h]] of DIMS) {
    const input = {
      label: `${sizeLabel} / ${dimLabel}`,
      standalone: true,
      cropSizes: [sizeObj],
      cropSizesRaw: JSON.stringify([sizeObj]),
      orig_w,
      orig_h,
      crop_w,
      crop_h,
    };
    vectors.push({ input, preState: PRE_STATE, output: run(input) });
  }
}

const SPECIALS = [
  {
    label: "not standalone: returns before touching the form",
    standalone: false,
    cropSizesRaw: JSON.stringify([SIZES[0][1]]),
    orig_w: 2000,
    orig_h: 1500,
    crop_w: 1600,
    crop_h: 1200,
  },
  {
    label: "empty sizes array: values blanked, placeholders untouched",
    standalone: true,
    cropSizesRaw: "[]",
    orig_w: 2000,
    orig_h: 1500,
    crop_w: 1600,
    crop_h: 1200,
  },
  {
    label: "two sizes: values blanked, placeholders untouched",
    standalone: true,
    cropSizesRaw: JSON.stringify([SIZES[0][1], SIZES[2][1]]),
    orig_w: 2000,
    orig_h: 1500,
    crop_w: 1600,
    crop_h: 1200,
  },
  {
    label: "unparseable sizes JSON: values blanked, placeholders untouched",
    standalone: true,
    cropSizesRaw: "not json",
    orig_w: 2000,
    orig_h: 1500,
    crop_w: 1600,
    crop_h: 1200,
  },
  {
    label: 'sizes is JSON null: typeof null is "object", $.isArray rejects it',
    standalone: true,
    cropSizesRaw: "null",
    orig_w: 2000,
    orig_h: 1500,
    crop_w: 1600,
    crop_h: 1200,
  },
  {
    label: "sizes is a JSON object, not an array",
    standalone: true,
    cropSizesRaw: JSON.stringify(SIZES[0][1]),
    orig_w: 2000,
    orig_h: 1500,
    crop_w: 1600,
    crop_h: 1200,
  },
];

for (const special of SPECIALS) {
  const input = { ...special, cropSizes: null };
  try {
    input.cropSizes = JSON.parse(special.cropSizesRaw);
  } catch {
    input.cropSizes = undefined;
  }
  vectors.push({ input, preState: PRE_STATE, output: run(input) });
}

// The width/height inputs missing entirely: the guard returns before the crop
// rows are revealed.
{
  const widthInput = document.getElementById("id_size-width");
  const heightInput = document.getElementById("id_size-height");
  const widthParent = widthInput.parentNode;
  const heightParent = heightInput.parentNode;
  resetForm();
  widthInput.remove();
  heightInput.remove();
  const input = {
    label: "size width/height inputs absent from the DOM",
    standalone: true,
    cropSizes: [SIZES[0][1]],
    cropSizesRaw: JSON.stringify([SIZES[0][1]]),
    orig_w: 2000,
    orig_h: 1500,
    crop_w: 1600,
    crop_h: 1200,
    sizeInputsPresent: false,
  };
  $("#id_standalone").prop("checked", true);
  $("#id_crop-sizes").val(input.cropSizesRaw);
  $("#id_crop-orig_w").val("2000");
  $("#id_crop-orig_h").val("1500");
  $("#id_thumbs-0-crop_w").val("1600");
  $("#id_thumbs-0-crop_h").val("1200");
  legacy.syncSizeForm();
  vectors.push({ input, preState: PRE_STATE, output: readForm() });
  widthParent.appendChild(widthInput);
  heightParent.appendChild(heightInput);
}

// ---------------------------------------------------------------------------
// Self-check: a handful of hand-computed outputs.
// ---------------------------------------------------------------------------

function selfCheck() {
  const failures = [];
  const byLabel = (label) => vectors.find((v) => v.input.label === label);

  const check = (label, expected) => {
    const vector = byLabel(label);
    if (!vector) {
      failures.push(`missing vector: ${label}`);
      return;
    }
    for (const [key, want] of Object.entries(expected)) {
      if (vector.output[key] !== want) {
        failures.push(
          `${label}: ${key} is ${JSON.stringify(vector.output[key])}, expected ${JSON.stringify(want)}`,
        );
      }
    }
  };

  // Untouched: the guard returns on the first line.
  check("not standalone: returns before touching the form", {
    widthValue: PRE_STATE.widthValue,
    heightValue: PRE_STATE.heightValue,
    widthPlaceholder: PRE_STATE.widthPlaceholder,
    heightPlaceholder: PRE_STATE.heightPlaceholder,
    rowsShown: false,
  });
  check("empty sizes array: values blanked, placeholders untouched", {
    widthValue: "",
    heightValue: "",
    widthPlaceholder: PRE_STATE.widthPlaceholder,
    rowsShown: false,
  });
  // round((600 / 1600) * 1204) == round(451.5) == 452, half up.
  check("w only / orig 2001x1501, crop 1600x1204", {
    widthValue: "600",
    heightValue: "",
    heightPlaceholder: "452",
    rowsShown: true,
  });
  // The placeholder scales from sizes[0].w (600), not from the max_w-clamped 300.
  check("w only, max_w below w / orig 2000x1500, crop 1600x1200", {
    widthValue: "600",
    heightPlaceholder: "450",
    rowsShown: true,
  });
  // Free size, crop 3000x2000 over both maxes: crop_scales [0.4, 0.45], the
  // larger wins (1350x900), then each dimension is clamped to its max.
  check("free, max_w+max_h / orig 3000x2000, crop 3000x2000", {
    widthValue: "",
    heightValue: "",
    widthPlaceholder: "1200",
    heightPlaceholder: "900",
    rowsShown: true,
  });
  // Free size, crop 800x600 under both maxes: the other branch, scaling
  // relative to the original image, smallest ratio wins:
  // min(1200/2000, 900/1500) == 0.6.
  check("free, max_w+max_h / orig 2000x1500, crop 800x600", {
    widthPlaceholder: "480",
    heightPlaceholder: "360",
    rowsShown: true,
  });
  // Same crop, no original dimensions: neither branch runs.
  check("free, max_w+max_h / no orig, crop 800x600", {
    widthPlaceholder: "800",
    heightPlaceholder: "600",
    rowsShown: true,
  });
  // No maxes at all: the crop box is the placeholder.
  check("free / orig 2000x1500, crop 1600x1200", {
    widthPlaceholder: "1600",
    heightPlaceholder: "1200",
    rowsShown: true,
  });
  // crop_w blank while crop_h exceeds max_h: the first branch still runs and
  // Math.max(1, Math.round(NaN * scale)) is NaN, so the placeholder is removed.
  check("free, max_h / orig 2000x1500, crop_w blank, crop_h 1200", {
    widthPlaceholder: null,
    heightPlaceholder: "900",
    rowsShown: false,
  });

  if (failures.length) {
    console.error("SELF-CHECK FAILED:");
    failures.forEach((f) => console.error(`  - ${f}`));
    process.exit(1);
  }
}

selfCheck();

writeGoldenJson(
  resolve(GOLDEN_DIR, "size-form-vectors.json"),
  {
    generatedFrom: generatedFromLabel(),
    generatedBy: "frontend/tests/legacy/extract-sizeform-vectors.mjs",
    description:
      "syncSizeForm() outputs from the unmodified 4.x dialog. `input` is the DOM state written before " +
      "the call (cropSizesRaw -> #id_crop-sizes, orig_w/orig_h -> #id_crop-orig_*, crop_w/crop_h -> " +
      '#id_thumbs-0-crop_*); `preState` is what the size form held beforehand, so that "left alone" is ' +
      'distinguishable from "set to empty"; `output` is #id_size-width / #id_size-height values and ' +
      "placeholders plus the inline display of the form#size .row.width / .row.height rows.",
    counts: { vectors: vectors.length },
    vectors,
  },
  ["vectors"],
);

console.log(`size-form-vectors.json: ${vectors.length} vectors; self-check OK`);
