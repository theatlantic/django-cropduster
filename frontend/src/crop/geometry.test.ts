import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import {
  aspectExtent,
  calcMinSize,
  clampCoordinates,
  clampToAspectBand,
  coerceExtent,
  defaultCropBox,
  fitToCrop,
  fixedAspectRatio,
} from "./geometry";
import type { CropBox, CropSelect, ExistingCrop, Size } from "./geometry";

/**
 * These vectors were recorded from the unmodified 4.x dialog running in
 * jsdom. Compare their JSON forms because both form serialization and JSON
 * convert `-0` to `0`.
 */

type JsonNumber = number | "Infinity" | "-Infinity" | "NaN";

interface Vector {
  input: {
    source: string;
    set: string;
    sizeIndex: number;
    sizeName: string;
    origW: number;
    origH: number;
    size: Size;
  };
  select: CropBox;
  setSelect: CropSelect;
  minSize: [number, number];
  deadLocalMinSize: [number, number];
  aspectRatio: number;
  aspectExtent: { min: JsonNumber; max: JsonNumber };
  aspectExtentRaw: { min: JsonNumber; max: JsonNumber };
  trueSize: [number, number];
  boxSize: [number, number];
}

interface PassthroughCase {
  kind: "existing-crop-passthrough";
  label: string;
  input: {
    origW: number;
    origH: number;
    size: Size;
    existingThumb: ExistingCrop;
    thumbInputsBefore: string;
  };
  setSelect: CropSelect;
  minSize: [number, number];
  thumbInputsAfter: Record<string, string>;
}

interface UpdateCoordinatesCase {
  kind: "update-coordinates";
  label: string;
  input: {
    coords: CropBox;
    jcropOptions: {
      minSize?: [number, number];
      maxSize?: [number, number];
    } | null;
  };
  select: CropBox;
}

interface GoldenFile {
  generatedFrom: string;
  counts: {
    sizeSets: number;
    sizes: number;
    sourceDims: number;
    vectors: number;
    edgeCases: number;
  };
  vectors: Vector[];
  edgeCases: (PassthroughCase | UpdateCoordinatesCase)[];
}

// Vite rewrites `new URL(<literal>, import.meta.url)` into an asset URL, hence
// the trip through fileURLToPath.
const goldenPath = resolve(
  dirname(fileURLToPath(import.meta.url)),
  "../../tests/golden/default-crop-vectors.json",
);
const golden = JSON.parse(readFileSync(goldenPath, "utf8")) as GoldenFile;

const vectors = golden.vectors;
const passthroughCases = golden.edgeCases.filter(
  (c): c is PassthroughCase => c.kind === "existing-crop-passthrough",
);
const updateCoordinateCases = golden.edgeCases.filter(
  (c): c is UpdateCoordinatesCase => c.kind === "update-coordinates",
);

function label(vector: Vector): string {
  const { source, set, sizeIndex, sizeName, origW, origH } = vector.input;
  return `${source}/${set}[${sizeIndex}] ${sizeName} @ ${origW}x${origH}`;
}

function compare(
  failures: string[],
  name: string,
  actual: unknown,
  expected: unknown,
): void {
  const got = JSON.stringify(actual);
  const want = JSON.stringify(expected);
  if (got !== want) {
    failures.push(`${name}: ${got} != ${want}`);
  }
}

function assertNoFailures(failures: string[]): void {
  expect(failures.slice(0, 20)).toEqual([]);
  expect(failures).toHaveLength(0);
}

/** JSON has no Infinity; the extractor serialized it as a string. */
function jsonNumber(value: number): JsonNumber {
  if (value === Infinity) return "Infinity";
  if (value === -Infinity) return "-Infinity";
  if (Number.isNaN(value)) return "NaN";
  return value;
}

/**
 * Mirror of the local `minSize` that `setCropOptions` builds and discards:
 * `calcMinSize` without the `required` filter on autos. Nothing in the port
 * computes this; it exists to prove the branch is dead.
 */
function allAutosMinSize(size: Size): [number, number] {
  let w = (size.min_w ?? 0) || (size.w ?? 0) || 0;
  let h = (size.min_h ?? 0) || (size.h ?? 0) || 0;
  for (const auto of size.auto ?? []) {
    w = Math.max(w, (auto.min_w ?? 0) || (auto.w ?? 0) || 0);
    h = Math.max(h, (auto.min_h ?? 0) || (auto.h ?? 0) || 0);
  }
  return [w, h];
}

describe("default-crop golden vectors", () => {
  it("loads every recorded vector", () => {
    expect(vectors).toHaveLength(golden.counts.vectors);
    expect(golden.edgeCases).toHaveLength(golden.counts.edgeCases);
    expect(golden.counts.vectors).toBeGreaterThanOrEqual(2114);
    expect(golden.counts.edgeCases).toBeGreaterThanOrEqual(13);
    expect(passthroughCases.length + updateCoordinateCases.length).toBe(
      golden.counts.edgeCases,
    );
  });

  it("calcMinSize reproduces Jcrop's minSize", () => {
    const failures: string[] = [];
    for (const vector of vectors) {
      compare(
        failures,
        label(vector),
        calcMinSize(vector.input.size),
        vector.minSize,
      );
    }
    assertNoFailures(failures);
  });

  it("aspectExtent reproduces getAspectRatioExtent, Infinity included", () => {
    const failures: string[] = [];
    for (const vector of vectors) {
      const extent = aspectExtent(vector.input.size);
      compare(
        failures,
        label(vector),
        { min: jsonNumber(extent.min), max: jsonNumber(extent.max) },
        vector.aspectExtentRaw,
      );
    }
    assertNoFailures(failures);
  });

  it("coerceExtent reproduces the extent getCropSelect sees", () => {
    const failures: string[] = [];
    for (const vector of vectors) {
      const extent = coerceExtent(aspectExtent(vector.input.size));
      compare(
        failures,
        label(vector),
        { min: jsonNumber(extent.min), max: jsonNumber(extent.max) },
        vector.aspectExtent,
      );
    }
    assertNoFailures(failures);
  });

  it("fixedAspectRatio reproduces the ratio handed to Jcrop", () => {
    const failures: string[] = [];
    for (const vector of vectors) {
      compare(
        failures,
        label(vector),
        fixedAspectRatio(vector.input.size),
        vector.aspectRatio,
      );
    }
    assertNoFailures(failures);
  });

  it("defaultCropBox reproduces the stored crop box", () => {
    const failures: string[] = [];
    for (const vector of vectors) {
      const { origW, origH, size } = vector.input;
      const result = defaultCropBox(origW, origH, size);
      compare(failures, `${label(vector)} box`, result.box, vector.select);
      compare(
        failures,
        `${label(vector)} setSelect`,
        result.setSelect,
        vector.setSelect,
      );
      compare(
        failures,
        `${label(vector)} fromExisting`,
        result.fromExisting,
        false,
      );
    }
    assertNoFailures(failures);
  });

  it("leaves setCropOptions' all-autos minSize dead", () => {
    const failures: string[] = [];
    let differing = 0;
    for (const vector of vectors) {
      compare(
        failures,
        `${label(vector)} dead local`,
        allAutosMinSize(vector.input.size),
        vector.deadLocalMinSize,
      );
      if (
        JSON.stringify(vector.deadLocalMinSize) !==
        JSON.stringify(vector.minSize)
      ) {
        differing += 1;
        compare(
          failures,
          `${label(vector)} minSize follows the live value`,
          calcMinSize(vector.input.size),
          vector.minSize,
        );
      }
    }
    // Size sets with an optional auto larger than their parent, which is where
    // the two values disagree.
    expect(differing).toBeGreaterThan(0);
    assertNoFailures(failures);
  });
});

describe("existing-crop passthrough", () => {
  it("returns the stored box untouched", () => {
    expect(passthroughCases).not.toHaveLength(0);
    for (const testCase of passthroughCases) {
      const { origW, origH, size, existingThumb } = testCase.input;
      const result = defaultCropBox(origW, origH, size, existingThumb);
      expect(result.setSelect, testCase.label).toEqual(testCase.setSelect);
      expect(result.fromExisting, testCase.label).toBe(true);
      expect(calcMinSize(size), testCase.label).toEqual(testCase.minSize);
      // The 4.x dialog returns before updateCoordinates, so the formset keeps
      // the values it was rendered with; `fromExisting` is that signal.
      for (const value of Object.values(testCase.thumbInputsAfter)) {
        expect(value, testCase.label).toBe(testCase.input.thumbInputsBefore);
      }
    }
  });

  it("does not treat a zero-filled thumb row as an existing crop", () => {
    const vector = vectors[0];
    expect(vector).toBeDefined();
    if (!vector) return;
    const { origW, origH, size } = vector.input;
    const result = defaultCropBox(origW, origH, size, {
      crop_x: 0,
      crop_y: 0,
      crop_w: 0,
      crop_h: 0,
    });
    expect(result.fromExisting).toBe(false);
    expect(result.box).toEqual(vector.select);
  });
});

describe("clampCoordinates", () => {
  it("reproduces updateCoordinates for every edge case", () => {
    expect(updateCoordinateCases).not.toHaveLength(0);
    for (const testCase of updateCoordinateCases) {
      const { coords, jcropOptions } = testCase.input;
      const box = clampCoordinates(coords, jcropOptions ?? {});
      expect(JSON.parse(JSON.stringify(box)), testCase.label).toEqual(
        testCase.select,
      );
    }
  });

  it("keeps Math.round(-0.5) negative zero, which never trips the clamp", () => {
    const box = clampCoordinates({ x: -0.5, y: -0.5, w: 100.4, h: 100.6 });
    expect(Object.is(box.x, -0)).toBe(true);
    expect(Object.is(box.y, -0)).toBe(true);
    // The width compensation the negative clamp applies did not run.
    expect(box.w).toBe(100);
    expect(box.h).toBe(101);
  });
});

/**
 * The recorded size sets do not configure `max_w` or `max_h`, so these cases
 * cover the remaining ratio clamps. Their expected values were recorded from
 * the unmodified 4.x `CropBoxClass` running in jsdom.
 */
describe("aspect band clamps the golden corpus does not reach", () => {
  function size(props: Size): Size {
    return {
      __type__: "Size",
      name: "x",
      label: "X",
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

  it("raises the lower bound from max_h, then widens the default crop to it", () => {
    const subject = size({ w: 600, max_h: 300 });
    expect(aspectExtent(subject)).toEqual({ min: 2, max: Infinity });
    expect(coerceExtent(aspectExtent(subject))).toEqual({ min: 2, max: 0 });
    expect(fixedAspectRatio(subject)).toBe(0);
    expect(calcMinSize(subject)).toEqual([600, 0]);

    // A square source is narrower than the 2:1 lower bound, so the box widens.
    const result = defaultCropBox(1000, 1000, subject);
    expect(result.box).toEqual({ x: 0, y: 250, w: 1000, h: 500 });
    expect(result.setSelect).toEqual([0, 250, 1000, 750]);
  });

  it("lowers the upper bound from max_w, then narrows the default crop to it", () => {
    const subject = size({ h: 300, max_w: 600 });
    expect(aspectExtent(subject)).toEqual({ min: 0, max: 2 });
    expect(calcMinSize(subject)).toEqual([0, 300]);

    const result = defaultCropBox(3000, 100, subject);
    expect(result.box).toEqual({ x: 1400, y: 0, w: 200, h: 100 });
    expect(result.setSelect).toEqual([1400, 0, 1600, 100]);
  });

  it("gates both max clamps behind the opposite dimension being set", () => {
    const subject = size({ max_w: 600, max_h: 300 });
    expect(aspectExtent(subject)).toEqual({ min: 0, max: Infinity });
    expect(defaultCropBox(1000, 1000, subject).box).toEqual({
      x: 0,
      y: 0,
      w: 1000,
      h: 1000,
    });
  });

  it("treats a min of exactly 1 as no minimum for the band only", () => {
    const sentinel = size({ h: 300, min_w: 1 });
    expect(aspectExtent(sentinel)).toEqual({ min: 0, max: Infinity });
    // calcMinSize has no such rule and takes the 1 at face value.
    expect(calcMinSize(sentinel)).toEqual([1, 300]);
    expect(defaultCropBox(3000, 100, sentinel).box).toEqual({
      x: 0,
      y: 0,
      w: 3000,
      h: 100,
    });

    const real = size({ h: 300, min_w: 600 });
    expect(aspectExtent(real)).toEqual({ min: 2, max: Infinity });
    expect(calcMinSize(real)).toEqual([600, 300]);
    expect(defaultCropBox(100, 3000, real).box).toEqual({
      x: 0,
      y: 1475,
      w: 100,
      h: 50,
    });
  });

  it("leaves an inverted band alone when the ratio is fixed", () => {
    const subject = size({ w: 600, h: 480, max_h: 240 });
    // min above max: nothing reconciles them, and Jcrop ignores both once
    // aspectRatio is set.
    expect(aspectExtent(subject)).toEqual({ min: 2.5, max: 1.25 });
    expect(fixedAspectRatio(subject)).toBe(1.25);
    expect(defaultCropBox(674, 800, subject).box).toEqual({
      x: 0,
      y: 131,
      w: 674,
      h: 539,
    });
  });

  it("ignores a required auto with no dimensions at all", () => {
    const subject = size({
      w: 600,
      h: 480,
      auto: [size({ name: "empty", required: true })],
    });
    expect(calcMinSize(subject)).toEqual([600, 480]);
  });

  it("locks an is_auto size's ratio while leaving its band open", () => {
    const subject = size({ w: 600, h: 480, is_auto: true });
    expect(aspectExtent(subject)).toEqual({ min: 0, max: Infinity });
    expect(fixedAspectRatio(subject)).toBe(1.25);
    expect(defaultCropBox(674, 800, subject).box).toEqual({
      x: 0,
      y: 131,
      w: 674,
      h: 539,
    });
  });
});

/**
 * The band clamp has no recorded vectors. It implements Jcrop's patched
 * `minAspectRatio`/`maxAspectRatio` options, whose behaviour was only ever
 * observable through a live drag. The rule it implements is Jcrop's own
 * (`getFixed`): the dimension the drag moved further is kept.
 */
describe("fitToCrop", () => {
  /**
   * Expected boxes computed by `Size.fit_to_crop()` itself
   * (`cropduster.resizing`, Python 3.12), so the seeded crops match what the
   * 4.x crop endpoint suggested for the same inputs.
   */
  const BOUNDS = { w: 1300, h: 1016 };
  const VECTORS: [string, Size, CropBox, CropBox][] = [
    [
      "free height from a wide crop",
      { name: "no_height", w: 600 },
      { x: 15, y: 0, w: 1270, h: 1016 },
      { x: 15, y: 0, w: 1270, h: 1016 },
    ],
    [
      "square from a wide crop",
      { name: "square", w: 500, h: 500 },
      { x: 15, y: 0, w: 1270, h: 1016 },
      { x: 142, y: 0, w: 1016, h: 1016 },
    ],
    [
      "minimums grow a small box and clamp to the origin",
      { name: "main", w: 600, h: 480 },
      { x: 100, y: 100, w: 300, h: 200 },
      { x: 0, y: 0, w: 600, h: 480 },
    ],
    [
      "pulled inside the far corner",
      { name: "wide", w: 600, h: 300 },
      { x: 1100, y: 900, w: 200, h: 116 },
      { x: 700, y: 716, w: 600, h: 300 },
    ],
    [
      "minimum scaling grows the reference",
      { name: "tall", w: 100, h: 400 },
      { x: 0, y: 0, w: 120, h: 80 },
      { x: 10, y: 0, w: 100, h: 400 },
    ],
    [
      "landscape reference to a portrait size",
      { name: "p", w: 300, h: 400 },
      { x: 200, y: 150, w: 900, h: 600 },
      { x: 332, y: 26, w: 636, h: 849 },
    ],
  ];

  for (const [label, size, reference, expected] of VECTORS) {
    it(label, () => {
      expect(fitToCrop(size, reference, BOUNDS)).toEqual(expected);
    });
  }

  it("declines a degenerate reference", () => {
    expect(
      fitToCrop(
        { name: "main", w: 600, h: 480 },
        { x: 0, y: 0, w: 0, h: 10 },
        BOUNDS,
      ),
    ).toBeNull();
  });
});

describe("clampToAspectBand", () => {
  const bounds = { w: 1000, h: 1000 };
  // A size 600 wide with a height between 400 and 800: ratios 0.75 to 1.5.
  const banded: Size = { name: "banded", w: 600, min_h: 400, max_h: 800 };

  it("describes the band the size accepts", () => {
    expect(coerceExtent(aspectExtent(banded))).toEqual({ min: 0.75, max: 1.5 });
  });

  it("leaves a box inside the band alone", () => {
    const box = { x: 0, y: 0, w: 600, h: 500 };
    expect(
      clampToAspectBand(box, { min: 0.75, max: 1.5 }, bounds, box),
    ).toEqual(box);
  });

  it("derives the height when the width is the dimension that moved", () => {
    const previous = { x: 0, y: 0, w: 600, h: 500 };
    const dragged = { x: 0, y: 0, w: 900, h: 500 };

    expect(
      clampToAspectBand(dragged, { min: 0.75, max: 1.5 }, bounds, previous),
    ).toEqual({ x: 0, y: 0, w: 900, h: 600 });
  });

  it("derives the width when the height is the dimension that moved", () => {
    const previous = { x: 0, y: 0, w: 600, h: 500 };
    const dragged = { x: 0, y: 0, w: 600, h: 200 };

    expect(
      clampToAspectBand(dragged, { min: 0.75, max: 1.5 }, bounds, previous),
    ).toEqual({ x: 0, y: 0, w: 300, h: 200 });
  });

  it("keeps the ratio when the derived dimension runs off the image", () => {
    // Widened along the bottom edge, where only 100px of height is left: the
    // derived 600px height is capped and the width follows it back down.
    const previous = { x: 0, y: 900, w: 600, h: 100 };
    const dragged = { x: 0, y: 900, w: 900, h: 100 };

    const clamped = clampToAspectBand(
      dragged,
      { min: 0.75, max: 1.5 },
      bounds,
      previous,
    );
    expect(clamped).toEqual({ x: 0, y: 900, w: 150, h: 100 });
    expect(clamped.w / clamped.h).toBe(1.5);
    expect(clamped.y + clamped.h).toBeLessThanOrEqual(bounds.h);
  });

  it("does nothing for a size with no band at all", () => {
    const box = { x: 0, y: 0, w: 10, h: 900 };
    expect(clampToAspectBand(box, { min: 0, max: 0 }, bounds, box)).toBe(box);
  });
});
