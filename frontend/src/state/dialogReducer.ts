/**
 * State transitions for upload and per-size cropping.
 *
 * Preserve two 4.x behaviors: never recalculate a crop that already has a box,
 * and retain crops from earlier steps when a later response omits them.
 */

import {
  calcMinSize,
  clampCoordinates,
  clampToAspectBand,
  coerceExtent,
  aspectExtent,
  defaultCropBox,
  fitToCrop,
  fixedAspectRatio,
} from "../crop/geometry";
import type { CropBox, Size } from "../crop/geometry";
import { displayScale, toDisplayPx, toSourcePx } from "../crop/scaling";
import type { DisplayScale } from "../crop/scaling";
import { canonicalToState } from "../formset/legacyPayload";
import type {
  CropDusterPayload,
  PayloadPreview,
} from "../formset/legacyPayload";
import { PRIMARY_SOURCE_ID } from "./types";
import type { CropEntry, DialogState, SourceImage, ThumbState } from "./types";
import type { DialogConfig, DialogThumbConfig } from "./dialogConfig";

/**
 * `DialogState` plus request and completion state owned by the dialog.
 * `preview` describes the server's rendition; canvas measurements are on the
 * primary source.
 */
export interface DialogModel extends DialogState {
  preview: PayloadPreview;
  /** Whether the file input holds a staged file. */
  fileSelected: boolean;
  /** Whether the dialog is still waiting for the state it opens on. */
  hydrating: boolean;
  /** Set once the last size has been cropped. */
  complete: boolean;
  /**
   * Whether the upload stage was entered from the crop stage to replace the
   * primary image. Existing crops stay untouched until the upload succeeds,
   * and Cancel returns to them.
   */
  replacing: boolean;
  /** Whether this session holds crop state the dialog did not open with. */
  dirty: boolean;
  /**
   * An object URL of the file just uploaded, shown behind the canvas while
   * the server preview named by `forDisplayUrl` is still downloading. The
   * dialog controller owns the URL's lifetime; this state only pairs it with
   * the preview it stands in for.
   */
  localPreview: { url: string; forDisplayUrl: string } | null;
}

/** The message is editor-facing; code and field are stable branch values. */
export interface DialogFailure {
  message: string;
  code: string | null;
  field: string | null;
}

const NO_ERROR = { error: null, errorCode: null, errorField: null };

function failed(failure: DialogFailure) {
  return {
    error: failure.message,
    errorCode: failure.code,
    errorField: failure.field,
  };
}

export type DialogAction =
  | { type: "hydrate"; config: DialogConfig }
  /** Existing-image modal state returned by the API. */
  | { type: "hydrated"; payload: CropDusterPayload }
  | { type: "hydrateFailed"; error: DialogFailure }
  | { type: "fileSelected"; selected: boolean }
  | { type: "uploadStarted" }
  | {
      type: "uploadSucceeded";
      payload: CropDusterPayload;
      /** Object URL of the uploaded file, for `DialogModel.localPreview`. */
      localPreviewUrl?: string | null;
    }
  | { type: "uploadFailed"; error: DialogFailure }
  /** Enter the upload stage to replace the primary image. */
  | { type: "beginReplace" }
  | { type: "cancelReplace" }
  /** Preview dimensions measured by the canvas. */
  | { type: "imageLoaded"; width: number; height: number }
  /** `box` is in the canvas's display pixels. */
  | { type: "boxChanged"; name: string; box: CropBox }
  | { type: "navigate"; delta: number }
  | { type: "navigateTo"; index: number }
  | { type: "cropSubmitStarted" }
  | { type: "cropSubmitSucceeded"; payload: CropDusterPayload }
  | { type: "cropSubmitFailed"; error: DialogFailure }
  | { type: "standaloneSizeChanged"; axis: "w" | "h"; value: number | null };

const EMPTY_SOURCE: SourceImage = {
  id: PRIMARY_SOURCE_ID,
  imageId: null,
  name: "",
  url: null,
  width: 0,
  height: 0,
  displayUrl: "",
  displaySrcset: null,
  displayWidth: 0,
  displayHeight: 0,
};

const EMPTY_PREVIEW: PayloadPreview = { url: null, width: null, height: null };

export const INITIAL_MODEL: DialogModel = {
  phase: "upload",
  standalone: false,
  sources: { [PRIMARY_SOURCE_ID]: EMPTY_SOURCE },
  sizes: [],
  index: 0,
  crops: {},
  thumbs: {},
  warnings: [],
  error: null,
  errorCode: null,
  errorField: null,
  preview: EMPTY_PREVIEW,
  fileSelected: false,
  hydrating: false,
  complete: false,
  replacing: false,
  dirty: false,
  localPreview: null,
};

/** Which of the two non-standalone scenes the dialog is showing. */
export function dialogStage(state: DialogState): "upload" | "crop" {
  return state.phase === "upload" || state.phase === "uploading"
    ? "upload"
    : "crop";
}

export function populatedCropCount(state: DialogState): number {
  return state.sizes.filter((size) => Boolean(state.crops[cropKey(size)]?.box))
    .length;
}

/**
 * The next size without a crop, searching forward from the current size and
 * wrapping, or -1 when every size is populated.
 */
export function nextPendingIndex(state: DialogState): number {
  const count = state.sizes.length;
  for (let offset = 1; offset <= count; offset += 1) {
    const index = (state.index + offset) % count;
    if (!state.crops[cropKey(state.sizes[index])]?.box) {
      return index;
    }
  }
  return -1;
}

export function primarySource(state: DialogState): SourceImage {
  return state.sources[PRIMARY_SOURCE_ID] ?? EMPTY_SOURCE;
}

export function currentSize(state: DialogState): Size | null {
  return state.sizes[state.index] ?? null;
}

/** The key `crops` holds a size's box under. */
export function cropKey(size: Size | null | undefined): string {
  return typeof size?.name === "string" ? size.name : "";
}

export function currentCrop(state: DialogState): CropEntry | null {
  return state.crops[cropKey(currentSize(state))] ?? null;
}

/** Source pixels per display pixel, or a 1:1 scale before the preview loads. */
export function sourceScale(state: DialogState): DisplayScale {
  const source = primarySource(state);
  if (!source.displayWidth || !source.displayHeight) {
    return { x: 1, y: 1 };
  }
  return displayScale(
    { w: source.width, h: source.height },
    { w: source.displayWidth, h: source.displayHeight },
  );
}

/**
 * The largest minimum any size imposes, for the "Min. size" help text.
 *
 * 4.x floored each axis at 1 so that a size set with no dimensions at all
 * still advertised something.
 */
export function overallMinSize(sizes: Size[]): [number, number] {
  const mins = sizes.map(calcMinSize);
  return [
    Math.max(0, ...mins.map((min) => min[0])) || 1,
    Math.max(0, ...mins.map((min) => min[1])) || 1,
  ];
}

export function allCropsPopulated(state: DialogState): boolean {
  return (
    state.sizes.length > 0 &&
    state.sizes.every((size) => Boolean(state.crops[cropKey(size)]?.box))
  );
}

function boxFrom(
  x: number | null,
  y: number | null,
  w: number | null,
  h: number | null,
): CropBox | null {
  if (!w || !h) {
    return null;
  }
  return { x: x ?? 0, y: y ?? 0, w, h };
}

/**
 * Make `index` current, seeding a crop only when it has none.
 *
 * The seed adapts the crop being left behind (`Size.fit_to_crop`, the box the
 * 4.x per-step crop endpoint suggested for each following step, which the
 * single-Save dialog must now derive itself), or the centered default when no
 * crop is populated yet.
 */
function enterSize(model: DialogModel, index: number): DialogModel {
  const size = model.sizes[index];
  const next = { ...model, index };
  if (!size) {
    return next;
  }
  const name = cropKey(size);
  if (next.crops[name]?.box) {
    return next;
  }
  const source = primarySource(next);
  if (!source.width || !source.height) {
    return next;
  }
  const reference =
    model.index === index
      ? null
      : (model.crops[cropKey(model.sizes[model.index])]?.box ?? null);
  const box =
    (reference &&
      fitToCrop(size, reference, { w: source.width, h: source.height })) ||
    defaultCropBox(source.width, source.height, size).box;
  return {
    ...next,
    // The seeded box is state the server does not hold yet.
    dirty: true,
    crops: {
      ...next.crops,
      [name]: { sourceId: PRIMARY_SOURCE_ID, box, changed: false },
    },
  };
}

function thumbFromConfig(
  entry: DialogThumbConfig,
  fallbackName: string,
): ThumbState {
  const name = entry.name || fallbackName;
  const box = boxFrom(entry.crop_x, entry.crop_y, entry.crop_w, entry.crop_h);
  return {
    id: entry.id,
    name,
    width: entry.width,
    height: entry.height,
    url: entry.rendererUrl ?? entry.url,
    fileUrl: entry.url,
    srcset: entry.srcset,
    crop: box && { x: box.x, y: box.y, width: box.w, height: box.h },
    ref: null,
    refId: null,
    tmp: false,
    changed: entry.changed,
    sourceId: PRIMARY_SOURCE_ID,
  };
}

export function hydrateModel(config: DialogConfig): DialogModel {
  const image = config.image;
  const source: SourceImage = {
    id: PRIMARY_SOURCE_ID,
    imageId: image?.id ?? null,
    name: image?.name ?? "",
    url: image?.url ?? null,
    width: image?.width ?? 0,
    height: image?.height ?? 0,
    displayUrl: config.preview.rendererUrl ?? config.preview.url ?? "",
    displaySrcset: config.preview.srcset ?? null,
    displayWidth: config.preview.w,
    displayHeight: config.preview.h,
  };

  const crops: Record<string, CropEntry> = {};
  const thumbs: Record<string, ThumbState> = {};

  // Restore earlier renditions, including their `auto` children.
  for (const [name, thumb] of Object.entries(config.cropThumbs)) {
    const fileUrl = typeof thumb.url === "string" ? thumb.url : null;
    const rendererUrl =
      typeof thumb.renderer_url === "string"
        ? thumb.renderer_url
        : typeof thumb.rendererUrl === "string"
          ? thumb.rendererUrl
          : null;
    const srcset = typeof thumb.srcset === "string" ? thumb.srcset : null;
    thumbs[name] = {
      id: thumb.id ?? null,
      name: thumb.name || name,
      width: thumb.width ?? null,
      height: thumb.height ?? null,
      url: rendererUrl ?? fileUrl,
      fileUrl,
      srcset,
      crop: null,
      ref: null,
      refId: null,
      tmp: false,
      changed: false,
      sourceId: PRIMARY_SOURCE_ID,
    };
  }

  // Load the step-aligned crop boxes.
  config.thumbs.forEach((entry, i) => {
    const name = cropKey(config.sizes[i]) || entry.name;
    const thumb = thumbFromConfig(entry, name);
    crops[name] = {
      sourceId: PRIMARY_SOURCE_ID,
      box: boxFrom(entry.crop_x, entry.crop_y, entry.crop_w, entry.crop_h),
      changed: false,
    };
    const known = thumbs[thumb.name];
    thumbs[thumb.name] = known
      ? {
          ...known,
          id: thumb.id ?? known.id,
          crop: thumb.crop ?? known.crop,
          width: thumb.width || known.width,
          height: thumb.height || known.height,
          url: thumb.url ?? known.url,
          fileUrl: thumb.fileUrl ?? known.fileUrl,
          srcset: thumb.srcset ?? known.srcset,
        }
      : thumb;
  });

  const model: DialogModel = {
    ...INITIAL_MODEL,
    phase: image ? "crop" : "upload",
    standalone: config.standalone,
    sources: { [PRIMARY_SOURCE_ID]: source },
    sizes: config.sizes,
    crops,
    thumbs,
    preview: {
      url: (config.preview.rendererUrl ?? config.preview.url) || null,
      file_url: config.preview.url || null,
      srcset: config.preview.srcset ?? null,
      width: config.preview.w || null,
      height: config.preview.h || null,
    },
    hydrating: Boolean(config.hydrate),
  };
  return enterSize(model, 0);
}

/**
 * Preserve measured display dimensions when a response keeps the same preview.
 * A new preview uses response dimensions until the canvas measures it.
 */
function mergeSource(previous: SourceImage, wire: SourceImage): SourceImage {
  // A response may omit the original's URL; keep the known one as long as the
  // response still describes the same file.
  const url = wire.url ?? (wire.name === previous.name ? previous.url : null);
  const measured = Boolean(previous.displayWidth && previous.displayHeight);
  const samePreview =
    !wire.displayUrl || wire.displayUrl === previous.displayUrl;
  if (!measured || !samePreview) {
    return { ...wire, url };
  }
  return {
    ...wire,
    url,
    displayUrl: previous.displayUrl,
    displaySrcset: wire.displaySrcset ?? previous.displaySrcset,
    displayWidth: previous.displayWidth,
    displayHeight: previous.displayHeight,
  };
}

/** Merge reported crops and thumbnails without removing earlier results. */
function applyPayload(
  model: DialogModel,
  payload: CropDusterPayload,
): DialogModel {
  const parsed = canonicalToState(payload, {
    sizes: payload.sizes?.length ? payload.sizes : model.sizes,
    standalone: model.standalone,
    index: model.index,
  });

  const previous = primarySource(model);
  const source = mergeSource(previous, primarySource(parsed));

  const thumbs = { ...model.thumbs, ...parsed.thumbs };
  const crops = { ...model.crops };
  for (const [name, entry] of Object.entries(parsed.crops)) {
    if (entry.box || !crops[name]) {
      crops[name] = entry;
    }
  }

  return {
    ...model,
    sources: { ...model.sources, [PRIMARY_SOURCE_ID]: source },
    sizes: parsed.sizes.length ? parsed.sizes : model.sizes,
    thumbs,
    crops,
    preview: parsed.preview,
    warnings: parsed.warnings,
    ...NO_ERROR,
  };
}

/**
 * Replace image-specific crops and thumbnails after upload. A standalone
 * upload's whole-image crop becomes the initial box, but not a saved thumbnail.
 */
function applyUpload(
  model: DialogModel,
  payload: CropDusterPayload,
  localPreviewUrl?: string | null,
): DialogModel {
  const fresh: DialogModel = {
    ...model,
    sources: { [PRIMARY_SOURCE_ID]: EMPTY_SOURCE },
    crops: {},
    thumbs: {},
    ...NO_ERROR,
    fileSelected: false,
  };

  const parsed = canonicalToState(payload, {
    sizes: payload.sizes?.length ? payload.sizes : model.sizes,
    standalone: model.standalone,
  });

  const crops: Record<string, CropEntry> = {};
  for (const [name, entry] of Object.entries(parsed.crops)) {
    if (entry.box) {
      crops[name] = { ...entry, changed: true };
    }
  }

  const displayUrl = primarySource(parsed).displayUrl;
  return enterSize(
    {
      ...fresh,
      phase: "crop",
      replacing: false,
      dirty: true,
      sources: parsed.sources,
      sizes: parsed.sizes.length ? parsed.sizes : model.sizes,
      crops,
      preview: parsed.preview,
      warnings: parsed.warnings,
      // An earlier upload's stand-in describes a preview no longer shown.
      localPreview:
        localPreviewUrl && displayUrl
          ? { url: localPreviewUrl, forDisplayUrl: displayUrl }
          : null,
    },
    0,
  );
}

function moveTo(model: DialogModel, index: number): DialogModel {
  if (model.phase !== "crop") {
    return model;
  }
  if (index < 0 || index >= model.sizes.length || index === model.index) {
    return model;
  }
  return enterSize(model, index);
}

/**
 * Convert a displayed crop to source pixels, then round once. Apply ratio bands
 * in display pixels and minimum-size snapping in source pixels.
 */
function commitBox(
  model: DialogModel,
  name: string,
  box: CropBox,
): DialogModel {
  const size = model.sizes.find((candidate) => cropKey(candidate) === name);
  if (!size) {
    return model;
  }
  const source = primarySource(model);
  const scale = sourceScale(model);
  const entry = model.crops[name];

  let display = box;
  if (!fixedAspectRatio(size)) {
    const previous = entry?.box
      ? toDisplayPx(entry.box, scale)
      : { x: 0, y: 0, w: 0, h: 0 };
    display = clampToAspectBand(
      box,
      coerceExtent(aspectExtent(size)),
      { w: source.displayWidth, h: source.displayHeight },
      previous,
    );
  }

  const clamped = clampCoordinates(toSourcePx(display, scale), {
    minSize: calcMinSize(size),
  });

  // Measurement and rounding can cause the scaled coordinates to exceed the
  // image dimensions by a pixel. Ensure that the final box stays within the
  // image boundaries.
  const bounded = { ...clamped };
  bounded.w = Math.min(bounded.w, source.width);
  bounded.h = Math.min(bounded.h, source.height);
  bounded.x = Math.min(bounded.x, source.width - bounded.w);
  bounded.y = Math.min(bounded.y, source.height - bounded.h);

  return {
    ...model,
    dirty: true,
    crops: {
      ...model.crops,
      [name]: {
        sourceId: entry?.sourceId ?? PRIMARY_SOURCE_ID,
        box: bounded,
        changed: true,
      },
    },
  };
}

/**
 * Update the standalone output size and mark its crop for regeneration. A
 * cleared dimension uses the 4.x `1` sentinel for no minimum.
 */
function applyStandaloneSize(
  model: DialogModel,
  axis: "w" | "h",
  value: number | null,
): DialogModel {
  const size = model.sizes[0];
  if (!size) {
    return model;
  }
  const updated: Size = {
    ...size,
    [axis]: value,
    [`min_${axis}`]: value || 1,
  };
  const name = cropKey(updated);
  const entry = model.crops[name];
  const crops = entry
    ? { ...model.crops, [name]: { ...entry, changed: true } }
    : model.crops;
  return enterSize(
    { ...model, dirty: true, sizes: [updated], index: 0, crops },
    0,
  );
}

export function dialogReducer(
  model: DialogModel,
  action: DialogAction,
): DialogModel {
  switch (action.type) {
    case "hydrate":
      return hydrateModel(action.config);

    case "hydrated": {
      const next = applyPayload({ ...model, hydrating: false }, action.payload);
      return enterSize(
        {
          ...next,
          phase: primarySource(next).name ? "crop" : "upload",
        },
        next.index,
      );
    }

    case "hydrateFailed":
      return { ...model, hydrating: false, ...failed(action.error) };

    case "fileSelected":
      return { ...model, fileSelected: action.selected };

    case "uploadStarted":
      return { ...model, phase: "uploading", ...NO_ERROR };

    case "uploadSucceeded":
      return applyUpload(model, action.payload, action.localPreviewUrl);

    case "uploadFailed":
      return {
        ...model,
        phase: "upload",
        fileSelected: model.standalone ? model.fileSelected : false,
        ...failed(action.error),
      };

    // Both directions leave crops, thumbs, and sources exactly as they are:
    // a replacement destroys nothing until its upload succeeds.
    case "beginReplace":
      if (model.phase !== "crop") {
        return model;
      }
      return {
        ...model,
        phase: "upload",
        replacing: true,
        fileSelected: false,
        ...NO_ERROR,
      };

    case "cancelReplace":
      if (!model.replacing || model.phase !== "upload") {
        return model;
      }
      return {
        ...model,
        phase: "crop",
        replacing: false,
        fileSelected: false,
        ...NO_ERROR,
      };

    case "imageLoaded": {
      const source = primarySource(model);
      return {
        ...model,
        sources: {
          ...model.sources,
          [PRIMARY_SOURCE_ID]: {
            ...source,
            displayWidth: action.width,
            displayHeight: action.height,
          },
        },
      };
    }

    case "boxChanged":
      return commitBox(model, action.name, action.box);

    case "navigate":
      return moveTo(model, model.index + action.delta);

    case "navigateTo":
      return moveTo(model, action.index);

    case "cropSubmitStarted":
      return { ...model, phase: "saving", ...NO_ERROR };

    case "cropSubmitSucceeded": {
      const next = applyPayload(model, action.payload);
      return { ...next, phase: "complete", complete: true, dirty: false };
    }

    case "cropSubmitFailed":
      return { ...model, phase: "crop", ...failed(action.error) };

    case "standaloneSizeChanged":
      return applyStandaloneSize(model, action.axis, action.value);
  }
}
