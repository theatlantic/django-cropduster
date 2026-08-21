/**
 * Centered edge resizing for fixed-aspect crops.
 *
 * react-image-crop's resize model is quadrant-anchored: every drag grows
 * toward a corner, which is why it hides the edge handles once an aspect is
 * locked. The 4.x dialog's Jcrop model defines what an edge handle does: the
 * opposite edge stays fixed, the dragged edge follows the pointer, and the
 * perpendicular axis grows and shrinks symmetrically about the selection's
 * midline, sliding along it when the image runs out of room.
 */

import type { PixelCrop } from "react-image-crop";

export type EdgeOrd = "n" | "e" | "s" | "w";

export function isEdgeOrd(value: unknown): value is EdgeOrd {
  return value === "n" || value === "e" || value === "s" || value === "w";
}

export interface EdgeResizeParams {
  ord: EdgeOrd;
  /** Requested length on the dragged axis: width for e/w, height for n/s. */
  primary: number;
  /**
   * The fixed opposite edge on the dragged axis: the west edge's x for "e",
   * the east edge's x for "w", the south edge's y for "n", the north edge's
   * y for "s".
   */
  anchor: number;
  /** The perpendicular midline the resize stays centered on. */
  center: number;
  /** The locked width / height ratio. Must be non-zero. */
  aspect: number;
  /** The rendered media size, which is the coordinate space of the crop. */
  bounds: { w: number; h: number };
  minWidth?: number;
  minHeight?: number;
  maxWidth?: number;
  maxHeight?: number;
}

function clamp(value: number, lower: number, upper: number): number {
  return Math.min(Math.max(value, lower), upper);
}

/**
 * The crop for an edge drag under a fixed aspect, unrounded.
 *
 * The demanded length never flips past the anchor; it bottoms out at the
 * minimums. A minimum that cannot fit yields the largest crop that does.
 */
export function edgeResizeCrop(params: EdgeResizeParams): PixelCrop {
  const { ord, anchor, center, aspect, bounds } = params;
  const horizontal = ord === "e" || ord === "w";

  // Work in units of width; a vertical demand converts through the aspect.
  const requested = horizontal ? params.primary : params.primary * aspect;

  const minWidth = Math.max(
    params.minWidth ?? 0,
    (params.minHeight ?? 0) * aspect,
  );
  // Room between the anchor and the image edge on the dragged axis; the
  // perpendicular axis may slide, so its whole dimension is available.
  const anchorRoom = horizontal
    ? ord === "e"
      ? bounds.w - anchor
      : anchor
    : (ord === "s" ? bounds.h - anchor : anchor) * aspect;
  let maxWidth = Math.min(anchorRoom, bounds.h * aspect, bounds.w);
  if (params.maxWidth) {
    maxWidth = Math.min(maxWidth, params.maxWidth);
  }
  if (params.maxHeight) {
    maxWidth = Math.min(maxWidth, params.maxHeight * aspect);
  }
  maxWidth = Math.max(maxWidth, 0);

  // `Math.min` last: when the minimum cannot fit, fitting wins.
  const width = Math.min(Math.max(requested, minWidth), maxWidth);
  const height = width / aspect;

  let x: number;
  let y: number;
  if (horizontal) {
    x = ord === "e" ? anchor : anchor - width;
    y = center - height / 2;
  } else {
    y = ord === "s" ? anchor : anchor - height;
    x = center - width / 2;
  }
  x = clamp(x, 0, Math.max(bounds.w - width, 0));
  y = clamp(y, 0, Math.max(bounds.h - height, 0));

  return { unit: "px", x, y, width, height };
}
