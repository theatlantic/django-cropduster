/**
 * Convert crop boxes between preview and source-image pixels.
 *
 * These functions do not round. The 4.x dialog rounded once after converting
 * back to source pixels, and rounding here too moves a crop on each trip.
 */

import type { CropBox } from "./geometry";

export interface Dimensions {
  w: number;
  h: number;
}

/** Source pixels per display pixel, per axis. */
export interface DisplayScale {
  x: number;
  y: number;
}

/** Source dimensions divided by the rendered preview dimensions. */
export function displayScale(
  source: Dimensions,
  display: Dimensions,
): DisplayScale {
  return { x: source.w / display.w, y: source.h / display.h };
}

/** Display pixels to source pixels, unrounded (Jcrop's `unscale`). */
export function toSourcePx(box: CropBox, scale: DisplayScale): CropBox {
  return {
    x: box.x * scale.x,
    y: box.y * scale.y,
    w: box.w * scale.x,
    h: box.h * scale.y,
  };
}

/** Source pixels to display pixels, unrounded (Jcrop's `setSelect`). */
export function toDisplayPx(box: CropBox, scale: DisplayScale): CropBox {
  return {
    x: box.x / scale.x,
    y: box.y / scale.y,
    w: box.w / scale.x,
    h: box.h / scale.y,
  };
}
