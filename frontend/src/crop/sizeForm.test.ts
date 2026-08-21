import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { syncSizeForm } from "./sizeForm";
import type { SizeFormSync } from "./sizeForm";

/**
 * `tests/golden/size-form-vectors.json` records what `syncSizeForm` did to the
 * standalone size form in the unmodified 4.x dialog. The port returns effects
 * instead of applying them, so each vector's recorded pre-state is replayed
 * through those effects and compared against the DOM the 4.x call left behind.
 */

interface SizeFormVector {
  input: {
    label: string;
    standalone: boolean;
    cropSizesRaw: string;
    orig_w: number | string;
    orig_h: number | string;
    crop_w: number | string;
    crop_h: number | string;
    sizeInputsPresent?: boolean;
  };
  preState: {
    widthValue: string;
    heightValue: string;
    widthPlaceholder: string;
    heightPlaceholder: string;
    rowDisplay: string;
  };
  output: {
    widthValue: string | null;
    heightValue: string | null;
    widthPlaceholder: string | null;
    heightPlaceholder: string | null;
    rowWidthDisplay: string;
    rowHeightDisplay: string;
    rowsShown: boolean;
  };
}

interface GoldenFile {
  generatedFrom: string;
  counts: { vectors: number };
  vectors: SizeFormVector[];
}

// Vite rewrites `new URL(<literal>, import.meta.url)` into an asset URL, hence
// the trip through fileURLToPath.
const goldenPath = resolve(
  dirname(fileURLToPath(import.meta.url)),
  "../../tests/golden/size-form-vectors.json",
);
const golden = JSON.parse(readFileSync(goldenPath, "utf8")) as GoldenFile;

const vectors = golden.vectors;

/** jQuery's `.show()` clears the inline display it was hiding the row with. */
const SHOWN_DISPLAY = "";

function applyToForm(
  vector: SizeFormVector,
  result: SizeFormSync,
): SizeFormVector["output"] {
  const pre = vector.preState;
  const present = vector.input.sizeInputsPresent ?? true;
  const rowDisplay = result.showRows ? SHOWN_DISPLAY : pre.rowDisplay;

  const placeholder = (
    update: SizeFormSync["widthPlaceholder"],
    previous: string,
  ): string | null => {
    switch (update.action) {
      case "set":
        return update.value;
      case "remove":
        return null;
      default:
        return previous;
    }
  };

  return {
    // A missing input reads back as null whatever the call did.
    widthValue: present ? (result.width ?? pre.widthValue) : null,
    heightValue: present ? (result.height ?? pre.heightValue) : null,
    widthPlaceholder: present
      ? placeholder(result.widthPlaceholder, pre.widthPlaceholder)
      : null,
    heightPlaceholder: present
      ? placeholder(result.heightPlaceholder, pre.heightPlaceholder)
      : null,
    rowWidthDisplay: rowDisplay,
    rowHeightDisplay: rowDisplay,
    rowsShown: result.showRows,
  };
}

describe("syncSizeForm golden vectors", () => {
  it("loads every recorded vector", () => {
    expect(vectors).toHaveLength(golden.counts.vectors);
    expect(golden.counts.vectors).toBeGreaterThanOrEqual(77);
  });

  it("reproduces the 4.x size form for every vector", () => {
    const failures: string[] = [];
    for (const vector of vectors) {
      const result = syncSizeForm({
        standalone: vector.input.standalone,
        sizesRaw: vector.input.cropSizesRaw,
        origW: String(vector.input.orig_w),
        origH: String(vector.input.orig_h),
        cropW: String(vector.input.crop_w),
        cropH: String(vector.input.crop_h),
        sizeInputsPresent: vector.input.sizeInputsPresent,
      });
      const got = JSON.stringify(applyToForm(vector, result));
      const want = JSON.stringify(vector.output);
      if (got !== want) {
        failures.push(`${vector.input.label}: ${got} != ${want}`);
      }
    }
    expect(failures.slice(0, 20)).toEqual([]);
    expect(failures).toHaveLength(0);
  });

  it("emits the 4.x NaN placeholder for an h-only size with no crop width", () => {
    const nanVectors = vectors.filter(
      (vector) => vector.output.widthPlaceholder === "NaN",
    );
    expect(nanVectors).not.toHaveLength(0);
    for (const vector of nanVectors) {
      const result = syncSizeForm({
        standalone: vector.input.standalone,
        sizesRaw: vector.input.cropSizesRaw,
        origW: String(vector.input.orig_w),
        origH: String(vector.input.orig_h),
        cropW: String(vector.input.crop_w),
        cropH: String(vector.input.crop_h),
      });
      expect(result.widthPlaceholder, vector.input.label).toEqual({
        action: "set",
        value: "NaN",
      });
    }
  });
});
