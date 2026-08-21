/**
 * Crop calculations ported from the 4.x dialog.
 *
 * Keep rounding in `clampCoordinates()`: moving it into the scale conversions
 * changes stored boxes by a pixel. The recorded vectors cover the 4.x
 * branches, including `Math.round(-0.5) === -0`.
 */

/** Values serialized from Python may be `null`. */
type SizeNumber = number | null | undefined;

/** A serialized `cropduster.resizing.Size`; unknown keys round-trip unchanged. */
export interface Size {
  __type__?: string;
  name?: string;
  label?: string;
  w?: SizeNumber;
  h?: SizeNumber;
  min_w?: SizeNumber;
  min_h?: SizeNumber;
  max_w?: SizeNumber;
  max_h?: SizeNumber;
  auto?: Size[] | null;
  required?: boolean | null;
  retina?: number | boolean | null;
  is_auto?: boolean | null;
  [key: string]: unknown;
}

/** The band of aspect ratios a size accepts, as Jcrop's min/maxAspectRatio. */
export interface AspectExtent {
  min: number;
  max: number;
}

/** A crop box in source-image pixels. */
export interface CropBox {
  x: number;
  y: number;
  w: number;
  h: number;
}

/** Jcrop's `setSelect`/`onSelect` box: `[x1, y1, x2, y2]`. */
export type CropSelect = [number, number, number, number];

/** A stored crop as it comes back from the formset or the crop endpoint. */
export interface ExistingCrop {
  crop_x?: number | string | null;
  crop_y?: number | string | null;
  crop_w?: number | string | null;
  crop_h?: number | string | null;
  [key: string]: unknown;
}

export interface DefaultCropResult {
  box: CropBox;
  setSelect: CropSelect;
  /**
   * True when the stored crop was returned unchanged. In that case the caller
   * must leave the formset values alone, matching the 4.x early return.
   */
  fromExisting: boolean;
}

/** The subset of Jcrop's options that `updateCoordinates` reads back. */
export interface CropSizeOptions {
  minSize?: readonly [number, number] | null;
  maxSize?: readonly [number, number] | null;
}

/** Preserve the truthiness checks used by the 4.x calculations. */
function truthy(value: unknown): boolean {
  return Boolean(value);
}

/** The 4.x calculations coerce missing values to 0. */
function toNumber(value: SizeNumber): number {
  return value ?? 0;
}

function toInt(value: number | string | null | undefined): number {
  return parseInt(String(value), 10);
}

/**
 * Port of `getAspectRatioExtent`. An unbounded maximum is `Infinity`, which
 * `coerceExtent()` converts to the zero sentinel expected by `getCropSelect()`.
 *
 * `min_w`/`min_h` widen the band only when greater than 1, since a minimum of
 * exactly 1 is the "no minimum" sentinel. `calcMinSize` has no such rule.
 */
export function aspectExtent(size: Size): AspectExtent {
  const aspect =
    !size.is_auto && truthy(size.w) && truthy(size.h)
      ? toNumber(size.w) / toNumber(size.h)
      : 0;
  let minAspect = aspect;
  let maxAspect = aspect || Infinity;

  if (truthy(size.w) && toNumber(size.min_h) > 1) {
    maxAspect = Math.min(maxAspect, toNumber(size.w) / toNumber(size.min_h));
  }
  if (truthy(size.w) && truthy(size.max_h)) {
    minAspect = Math.max(minAspect, toNumber(size.w) / toNumber(size.max_h));
  }
  if (truthy(size.h) && toNumber(size.min_w) > 1) {
    minAspect = Math.max(minAspect, toNumber(size.min_w) / toNumber(size.h));
  }
  if (truthy(size.h) && truthy(size.max_w)) {
    maxAspect = Math.min(maxAspect, toNumber(size.max_w) / toNumber(size.h));
  }

  return { min: minAspect, max: maxAspect };
}

/**
 * Convert an unbounded maximum to the zero sentinel used by `getCropSelect()`.
 * Leaving it as `Infinity` produces a zero-height crop.
 */
export function coerceExtent(extent: AspectExtent): AspectExtent {
  return {
    min: extent.min,
    max: extent.max === Infinity ? 0 : extent.max,
  };
}

/**
 * The fixed aspect ratio `setCropOptions` passes to Jcrop, or 0 when the size
 * is free in one dimension.
 *
 * Unlike `aspectExtent`, this ignores `is_auto`: an auto size with both
 * dimensions still gets a locked ratio while its extent band stays open.
 */
export function fixedAspectRatio(size: Size): number {
  return truthy(size.w) && truthy(size.h)
    ? toNumber(size.w) / toNumber(size.h)
    : 0;
}

/**
 * Port of `calcMinSize()`. Only required auto sizes increase the minimum.
 */
export function calcMinSize(size: Size): [number, number] {
  const minSize: [number, number] = [
    toNumber(size.min_w) || toNumber(size.w) || 0,
    toNumber(size.min_h) || toNumber(size.h) || 0,
  ];
  for (const autoSize of size.auto ?? []) {
    if (!autoSize.required) {
      continue;
    }
    const minW = toNumber(autoSize.min_w) || toNumber(autoSize.w) || 0;
    const minH = toNumber(autoSize.min_h) || toNumber(autoSize.h) || 0;
    minSize[0] = Math.max(minSize[0], minW);
    minSize[1] = Math.max(minSize[1], minH);
  }
  return minSize;
}

/**
 * Return a stored crop unchanged, or calculate the largest centered crop
 * allowed by the size's fixed ratio or ratio range.
 */
export function defaultCropBox(
  origW: number,
  origH: number,
  size: Size,
  existing?: ExistingCrop | null,
): DefaultCropResult {
  if (existing && truthy(existing.crop_w) && truthy(existing.crop_h)) {
    const x = toInt(existing.crop_x);
    const y = toInt(existing.crop_y);
    const w = toInt(existing.crop_w);
    const h = toInt(existing.crop_h);
    return {
      box: { x, y, w, h },
      setSelect: [x, y, x + w, y + h],
      fromExisting: true,
    };
  }

  let aspectRatio = fixedAspectRatio(size);
  const extent = coerceExtent(aspectExtent(size));

  let x: number;
  let y: number;
  let w: number;
  let h: number;

  if (!aspectRatio) {
    x = 0;
    y = 0;
    w = origW;
    h = origH;
    aspectRatio = w / h;
    if (extent.min && aspectRatio < extent.min) {
      aspectRatio = extent.min;
    } else if (extent.max && aspectRatio > extent.max) {
      aspectRatio = extent.max;
    }
  }

  if (origW / origH < aspectRatio) {
    x = 0;
    w = origW;
    h = Math.round(w / aspectRatio);
    y = Math.round((origH - h) / 2);
  } else {
    y = 0;
    h = origH;
    w = Math.round(h * aspectRatio);
    x = Math.round((origW - w) / 2);
  }

  return {
    box: { x, y, w, h },
    setSelect: [x, y, x + w, y + h],
    fromExisting: false,
  };
}

/** Python's `int(round(x))`: banker's rounding, half to even. */
function pyRound(value: number): number {
  const floor = Math.floor(value);
  const diff = value - floor;
  if (diff > 0.5) {
    return floor + 1;
  }
  if (diff < 0.5) {
    return floor;
  }
  return floor % 2 === 0 ? floor : floor + 1;
}

/**
 * Port of `Size.fit_to_crop()` over `Crop.best_fit()`: the size's best fit
 * within `reference`, centered on it and pulled inside `bounds`.
 *
 * This is the box the 4.x crop endpoint suggested for each later step, which
 * the single-Save dialog derives client-side when it seeds a size. Wire
 * sizes never include `min_aspect`/`max_aspect`, but they are honored when
 * present. `max_w`/`max_h` are accepted and ignored, as in `best_fit()`.
 * Returns null for a degenerate reference; the caller falls back to
 * `defaultCropBox()`.
 */
export function fitToCrop(
  size: Size,
  reference: CropBox,
  bounds: { w: number; h: number },
): CropBox | null {
  if (reference.w <= 0 || reference.h <= 0) {
    return null;
  }

  const sizeW = toNumber(size.w);
  const sizeH = toNumber(size.h);
  // `fit_to_crop` floors each minimum at the size's own dimension.
  const minW = toNumber(size.min_w) || sizeW;
  const minH = toNumber(size.min_h) || sizeH;
  const minAspect = toNumber(size.min_aspect as SizeNumber);
  const maxAspect = toNumber(size.max_aspect as SizeNumber);

  const boxAspect = reference.w / reference.h;
  let aspect = sizeW && sizeH ? sizeW / sizeH : boxAspect;
  if (minAspect && aspect < minAspect) {
    aspect = minAspect;
  } else if (maxAspect && aspect > maxAspect) {
    aspect = maxAspect;
  }

  const scale = Math.sqrt(aspect / boxAspect);
  let w = reference.w * scale;
  let h = w / aspect;

  const minScales: number[] = [];
  if (minW && minW > w) {
    minScales.push(minW / w);
  }
  if (minH && minH > h) {
    minScales.push(minH / h);
  }
  if (minScales.length) {
    const minScale = Math.max(...minScales);
    w *= minScale;
    h *= minScale;
  }

  const midX = reference.x + reference.w / 2;
  const midY = reference.y + reference.h / 2;
  let x1 = midX - w / 2;
  let y1 = midY - h / 2;
  let x2 = x1 + w;
  let y2 = y1 + h;
  const initialW = x2 - x1;
  const initialH = y2 - y1;

  let scaleX = 1;
  let scaleY = 1;
  if (x1 < 0) {
    x2 += -x1;
    x1 = 0;
  }
  if (x2 > bounds.w) {
    x1 = Math.max(bounds.w - initialW, 0);
    x2 = bounds.w;
    scaleX = (x2 - x1) / initialW;
  }
  if (y1 < 0) {
    y2 += -y1;
    y1 = 0;
  }
  if (y2 > bounds.h) {
    y1 = Math.max(bounds.h - initialH, 0);
    y2 = bounds.h;
    scaleY = (y2 - y1) / initialH;
  }

  if (scaleY < scaleX) {
    // Scale down the width to keep the ratio, but never below min_w.
    w = (x2 - x1) * (scaleY / scaleX);
    if (w < minW) {
      w = minW;
    }
    x1 += (initialW - w) / 2;
    x2 = x1 + w;
  } else {
    // Scale down the height to keep the ratio, but never below min_h.
    h = (y2 - y1) * (scaleX / scaleY);
    if (h < minH) {
      h = minH;
    }
    y1 += (initialH - h) / 2;
    y2 = y1 + h;
  }

  const wR = pyRound(w);
  const hR = pyRound(h);
  let x1R = Math.max(pyRound(x1), 0);
  let y1R = Math.max(pyRound(y1), 0);
  let x2R = Math.min(pyRound(x2), bounds.w, x1R + wR);
  let y2R = Math.min(pyRound(y2), bounds.h, y1R + hR);

  // Fix off-by-one rounding errors, as `best_fit()` does.
  if (x2R - x1R === wR - 1) {
    if (x2R < bounds.w) {
      x2R += 1;
    } else if (x1R > 0) {
      x1R -= 1;
    }
  }
  if (y2R - y1R === hR - 1) {
    if (y2R < bounds.h) {
      y2R += 1;
    } else if (y1R > 0) {
      y1R -= 1;
    }
  }

  return { x: x1R, y: y1R, w: x2R - x1R, h: y2R - y1R };
}

/**
 * Clamp a crop to a size's allowed ratio range.
 *
 * Preserve the dimension that moved farther and derive the other. If the
 * result exceeds the image bounds, cap it and recalculate its partner.
 */
export function clampToAspectBand(
  box: CropBox,
  extent: AspectExtent,
  bounds: { w: number; h: number },
  previous: CropBox,
): CropBox {
  if (!extent.min && !extent.max) {
    return box;
  }
  if (!box.w || !box.h) {
    return box;
  }

  const ratio = box.w / box.h;
  let aspect: number;
  if (extent.min && ratio < extent.min) {
    aspect = extent.min;
  } else if (extent.max && ratio > extent.max) {
    aspect = extent.max;
  } else {
    return box;
  }

  const movedX = Math.abs(box.w - previous.w);
  const movedY = Math.abs(box.h - previous.h);

  let { w, h } = box;
  if (movedX > movedY) {
    h = w / aspect;
  } else {
    w = h * aspect;
  }

  const maxW = bounds.w - box.x;
  const maxH = bounds.h - box.y;
  if (h > maxH) {
    h = maxH;
    w = h * aspect;
  }
  if (w > maxW) {
    w = maxW;
    h = w / aspect;
  }

  return { x: box.x, y: box.y, w, h };
}

/**
 * `updateCoordinates`: rounds an incoming selection, pulls a box that starts
 * outside the top/left edge back inside by shrinking it, then snaps a width or
 * height that is exactly one pixel off a min/max size onto that size.
 *
 * Order matters: the negative clamp runs first, so the snapping sees its ±1
 * width compensation. `Math.round(-0.5)` is `-0`, which is not `< 0`, so a
 * coordinate that rounds to negative zero is left alone; writing it to the
 * formset or to JSON renders it as "0".
 */
export function clampCoordinates(
  coords: CropBox,
  options: CropSizeOptions = {},
): CropBox {
  let x = Math.round(coords.x);
  let y = Math.round(coords.y);
  let w = Math.round(coords.w);
  let h = Math.round(coords.h);

  if (y < 0) {
    h += y;
    y = 0;
  }
  if (x < 0) {
    w += x;
    x = 0;
  }

  const { minSize, maxSize } = options;
  if (minSize) {
    if (Math.abs(w - minSize[0]) === 1) {
      w = minSize[0];
    }
    if (Math.abs(h - minSize[1]) === 1) {
      h = minSize[1];
    }
  }
  if (maxSize) {
    if (Math.abs(w - maxSize[0]) === 1) {
      w = maxSize[0];
    }
    if (Math.abs(h - maxSize[1]) === 1) {
      h = maxSize[1];
    }
  }

  return { x, y, w, h };
}
