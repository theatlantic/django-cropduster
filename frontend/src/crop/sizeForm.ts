/**
 * Calculate the standalone size-form updates made by the 4.x dialog.
 *
 * Returning the changes instead of writing to the DOM lets tests distinguish
 * an untouched value from one cleared to an empty string.
 */

import type { Size } from "./geometry";

export interface SizeFormInput {
  /** Whether `#id_standalone` is checked. */
  standalone: boolean;
  /** Raw `#id_crop-sizes` value. */
  sizesRaw: string;
  /** Raw `#id_crop-orig_w` / `#id_crop-orig_h` values. */
  origW: string;
  origH: string;
  /** Raw `#id_thumbs-0-crop_w` / `#id_thumbs-0-crop_h` values. */
  cropW: string;
  cropH: string;
  /** False when `#id_size-width`/`#id_size-height` are absent. */
  sizeInputsPresent?: boolean;
}

export type PlaceholderUpdate =
  { action: "keep" } | { action: "set"; value: string } | { action: "remove" };

export interface SizeFormSync {
  /** False when the standalone guard returned before touching anything. */
  touched: boolean;
  /** Value written to `#id_size-width`, or null when nothing was written. */
  width: string | null;
  /** Value written to `#id_size-height`, or null when nothing was written. */
  height: string | null;
  widthPlaceholder: PlaceholderUpdate;
  heightPlaceholder: PlaceholderUpdate;
  /** Whether the `.row.width` / `.row.height` rows were revealed. */
  showRows: boolean;
}

const KEEP: PlaceholderUpdate = { action: "keep" };
const REMOVE: PlaceholderUpdate = { action: "remove" };

function set(value: number): PlaceholderUpdate {
  return { action: "set", value: String(value) };
}

function truthy(value: unknown): boolean {
  return Boolean(value);
}

function toNumber(value: number | null | undefined): number {
  return value ?? 0;
}

function parseSizes(raw: string): unknown {
  try {
    return JSON.parse(raw) as unknown;
  } catch {
    // 4.x swallows the parse error and leaves `sizes` undefined, which the
    // guard below rejects.
    return undefined;
  }
}

export function syncSizeForm(input: SizeFormInput): SizeFormSync {
  if (!input.standalone) {
    return {
      touched: false,
      width: null,
      height: null,
      widthPlaceholder: KEEP,
      heightPlaceholder: KEEP,
      showRows: false,
    };
  }

  const sizes = parseSizes(input.sizesRaw);
  const inputsPresent = input.sizeInputsPresent ?? true;

  // Both values are blanked before either guard below, so a size list that the
  // dialog cannot use still clears the form (placeholders are left alone).
  const blanked = inputsPresent ? "" : null;
  const cleared: SizeFormSync = {
    touched: true,
    width: blanked,
    height: blanked,
    widthPlaceholder: KEEP,
    heightPlaceholder: KEEP,
    showRows: false,
  };

  if (
    typeof sizes !== "object" ||
    !Array.isArray(sizes) ||
    sizes.length !== 1
  ) {
    return cleared;
  }
  if (!inputsPresent) {
    return cleared;
  }

  const size = (sizes as Size[])[0] as Size;
  const width = truthy(size.w) ? String(size.w) : "";
  const height = truthy(size.h) ? String(size.h) : "";

  const origW = parseInt(input.origW, 10) || 0;
  const origH = parseInt(input.origH, 10) || 0;
  let cropW = parseInt(input.cropW, 10);
  let cropH = parseInt(input.cropH, 10);

  const showRows = truthy(cropW && cropH);

  const result: SizeFormSync = {
    touched: true,
    width,
    height,
    widthPlaceholder: KEEP,
    heightPlaceholder: KEEP,
    showRows,
  };

  // The values are read back off the inputs as strings, so `Math.min` coerces
  // them: a blank input becomes the number 0 whenever a max is configured.
  let userWidth: string | number = width;
  let userHeight: string | number = height;
  if (truthy(size.max_w)) {
    userWidth = Math.min(toNumber(size.max_w), Number(userWidth));
  }
  if (truthy(size.max_h)) {
    userHeight = Math.min(toNumber(size.max_h), Number(userHeight));
  }

  if (userWidth && !userHeight && cropW) {
    // 4.x uses the unclamped `size.w` here, so preserve that value rather than
    // `userWidth`.
    result.heightPlaceholder = set(
      Math.round((toNumber(size.w) / cropW) * cropH),
    );
  } else if (userHeight && !userWidth && cropH) {
    // If `cropW` is blank, the 4.x calculation produces a "NaN" placeholder.
    result.widthPlaceholder = set(
      Math.round((toNumber(size.h) / cropH) * cropW),
    );
  } else if (!userWidth && !userHeight) {
    // The unparenthesized 4.x condition parses as
    //   (cropW && cropH && (max_w && cropW > max_w)) || (max_h && cropH > max_h)
    // A blank crop_w with an over-limit crop_h therefore reaches this branch
    // and propagates NaN into the width.
    if (
      (cropW && cropH && truthy(size.max_w) && cropW > toNumber(size.max_w)) ||
      (truthy(size.max_h) && cropH > toNumber(size.max_h))
    ) {
      // Scale the crop box down by the largest applicable ratio, then clamp.
      const cropScales: number[] = [];
      if (truthy(size.max_w) && toNumber(size.max_w) < cropW) {
        cropScales.push(toNumber(size.max_w) / cropW);
      }
      if (truthy(size.max_h) && toNumber(size.max_h) < cropH) {
        cropScales.push(toNumber(size.max_h) / cropH);
      }
      if (cropScales.length) {
        const cropScale = Math.max(...cropScales);
        cropW = Math.max(1, Math.round(cropW * cropScale));
        cropH = Math.max(1, Math.round(cropH * cropScale));
        if (truthy(size.max_w)) {
          cropW = Math.min(toNumber(size.max_w), cropW);
        }
        if (truthy(size.max_h)) {
          cropH = Math.min(toNumber(size.max_h), cropH);
        }
      }
    } else if (origW && origH && cropW && cropH) {
      // Scale by the smallest ratio, relative to the original rather than the
      // crop box.
      const maxScales: number[] = [];
      if (truthy(size.max_w) && toNumber(size.max_w) < origW) {
        maxScales.push(toNumber(size.max_w) / origW);
      }
      if (truthy(size.max_h) && toNumber(size.max_h) < origH) {
        maxScales.push(toNumber(size.max_h) / origH);
      }
      if (maxScales.length) {
        const maxScale = Math.min(...maxScales);
        cropW = Math.max(1, Math.round(cropW * maxScale));
        cropH = Math.max(1, Math.round(cropH * maxScale));
        if (truthy(size.max_w)) {
          cropW = Math.min(toNumber(size.max_w), cropW);
        }
        if (truthy(size.max_h)) {
          cropH = Math.min(toNumber(size.max_h), cropH);
        }
      }
    }

    result.widthPlaceholder = cropW ? set(cropW) : REMOVE;
    result.heightPlaceholder = cropH ? set(cropH) : REMOVE;
  }

  return result;
}
