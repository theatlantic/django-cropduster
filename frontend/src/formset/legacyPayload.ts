/**
 * Convert between the v1 API response, dialog state, and the 4.x object passed
 * to `CropDuster.complete()`.
 *
 * Existing integrations still consume the 4.x fields, so completion converts
 * the result only after the dialog has finished.
 */

import type { Size } from "../crop/geometry";
import { DEFAULT_PREVIEW_SIZE } from "../state/dialogConfig";
import type {
  CropEntry,
  DialogState,
  SourceImage,
  ThumbCrop,
  ThumbState,
} from "../state/types";
import { PRIMARY_SOURCE_ID } from "../state/types";

// ---------------------------------------------------------------------------
// 4.x completion and endpoint responses
// ---------------------------------------------------------------------------

/** An entry of `crop.thumbs`, which is what `setThumbnails` consumes. */
export interface LegacyThumb {
  id: number | null;
  name: string;
  width: number | null;
  height: number | null;
  url?: string;
  [key: string]: unknown;
}

export interface LegacyCropData {
  image_id: number | null;
  orig_image: string | null;
  orig_w: number | null;
  orig_h: number | null;
  /** Keyed by raw size name, including reference thumbs. */
  thumbs: Record<string, LegacyThumb>;
  /** A JSON string in the standalone upload response, a list elsewhere. */
  sizes?: string | Size[] | null;
  standalone?: boolean;
  [key: string]: unknown;
}

/**
 * One entry of the vestigial top-level `thumbs` list: a `ThumbForm`'s
 * `cleaned_data` with the crop view's updates merged in.
 */
export interface LegacyThumbForm {
  id: number | null;
  name: string;
  width?: number | null;
  height?: number | null;
  crop_x?: number | null;
  crop_y?: number | null;
  crop_w?: number | null;
  crop_h?: number | null;
  changed?: boolean;
  url?: string;
  thumbs?: Record<string, LegacyThumb>;
  [key: string]: unknown;
}

/** The payload passed to `CropDuster.complete`. */
export interface LegacyCompletePayload {
  crop: LegacyCropData;
  thumbs: LegacyThumbForm[];
  initial: boolean;
  preview_url: string;
  preview_w: number;
  preview_h: number;
  [key: string]: unknown;
}

/**
 * The `/cropduster/upload/` response, which the dialog no longer asks for.
 *
 * Kept because the endpoint is still served for downstream rich-text
 * clients that build those POSTs by hand, and because the recorded responses
 * are test input.
 */
export interface LegacyUploadResponse {
  crop: LegacyCropData;
  url: string;
  orig_image: string;
  orig_w: number;
  orig_h: number;
  width: number;
  height: number;
  [key: string]: unknown;
}

// ---------------------------------------------------------------------------
// v1 API response
// ---------------------------------------------------------------------------

export interface PayloadImage {
  id: number | null;
  name: string;
  url: string | null;
  width: number | null;
  height: number | null;
  field_identifier: string;
  content_type_id: number | null;
  object_id: number | string | null;
}

export interface PayloadPreview {
  /** Renderer-routed, exactly as `PayloadThumb.url` is. */
  url: string | null;
  width: number | null;
  height: number | null;
  /** Higher-density renderer candidates for the crop UI preview. */
  srcset?: string | null;
  /** The storage file, whatever the renderer would address the preview by. */
  file_url?: string | null;
}

export interface PayloadCrop {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface PayloadThumb {
  id: number | null;
  name: string;
  width: number | null;
  height: number | null;
  crop: PayloadCrop | null;
  /** Name of the thumb this one is a rendition of. */
  ref: string | null;
  ref_id: number | null;
  /** Renderer-routed, so it may be cache-busted or on another host entirely. */
  url: string | null;
  srcset: string | null;
  /** The storage file, whatever the renderer would address the crop by. */
  file_url?: string | null;
  tmp: boolean;
  changed: boolean;
  /** Reserved for per-crop override sources; null through 5.x. */
  source: string | null;
}

export interface PayloadMetadata {
  attribution: string | null;
  attribution_link: string | null;
  caption: string | null;
  alt_text: string | null;
}

export interface PayloadWarning {
  /** Null for a warning the service layer raised as bare prose. */
  code: string | null;
  message: string;
}

export interface CropDusterPayload {
  version: 1;
  image: PayloadImage | null;
  preview: PayloadPreview | null;
  sizes: Size[];
  /** Keyed by raw size name. */
  thumbs: Record<string, PayloadThumb>;
  metadata: PayloadMetadata;
  warnings: PayloadWarning[];
}

// ---------------------------------------------------------------------------
// Conversions
// ---------------------------------------------------------------------------

/** The dialog's view of a v1 response. */
export interface CanonicalState extends DialogState {
  /**
   * The preview rendition as the *server* describes it.
   *
   * Not the dimensions the canvas is drawing at: a shell is free to scale the
   * preview down to fit, and `SourceImage.displayWidth`/`displayHeight` are
   * what it measured. These are what the widget stores and renders the
   * thumbnail strip at, which is why the two are kept apart.
   */
  preview: PayloadPreview;
}

export interface CanonicalToStateOptions {
  /**
   * The size set the crops answer to. Falls back to the payload's own, which
   * every endpoint echoes.
   */
  sizes?: Size[];
  standalone?: boolean;
  index?: number;
}

function boxOf(crop: PayloadCrop | null | undefined): ThumbCrop | null {
  if (!crop || !crop.width || !crop.height) {
    return null;
  }
  return { x: crop.x, y: crop.y, width: crop.width, height: crop.height };
}

function thumbFromPayload(name: string, thumb: PayloadThumb): ThumbState {
  return {
    id: thumb.id ?? null,
    name: thumb.name || name,
    width: thumb.width ?? null,
    height: thumb.height ?? null,
    url: thumb.url ?? null,
    fileUrl: thumb.file_url ?? null,
    srcset: thumb.srcset ?? null,
    crop: boxOf(thumb.crop),
    ref: thumb.ref ?? null,
    refId: thumb.ref_id ?? null,
    tmp: Boolean(thumb.tmp),
    changed: Boolean(thumb.changed),
    sourceId: PRIMARY_SOURCE_ID,
  };
}

/**
 * The crop a size stands for, out of a set keyed by thumb name.
 *
 * The two names are the same everywhere but standalone, where the rendition is
 * named after its own contents and shares no key with the size that asked for
 * it. There is exactly one size in that mode, so the one crop that is not a
 * rendition of another is the answer.
 */
export function thumbForSize(
  thumbs: Record<string, ThumbState>,
  size: Size | null | undefined,
  options: { standalone?: boolean } = {},
): ThumbState | null {
  const name = typeof size?.name === "string" ? size.name : "";
  const byName = thumbs[name];
  if (byName) {
    return byName;
  }
  if (!options.standalone) {
    return null;
  }
  return Object.values(thumbs).find((thumb) => !thumb.ref) ?? null;
}

/**
 * Build dialog state from a v1 response.
 *
 * A crop without a primary key is a server suggestion rather than a rendered
 * file, so mark it changed for the next crop request.
 */
export function canonicalToState(
  payload: CropDusterPayload,
  options: CanonicalToStateOptions = {},
): CanonicalState {
  const image = payload.image;
  const preview: PayloadPreview = payload.preview ?? {
    url: null,
    width: null,
    height: null,
    srcset: null,
    file_url: null,
  };
  const source: SourceImage = {
    id: PRIMARY_SOURCE_ID,
    imageId: image?.id ?? null,
    name: image?.name ?? "",
    url: image?.url ?? null,
    width: image?.width ?? 0,
    height: image?.height ?? 0,
    displayUrl: preview.url ?? "",
    displaySrcset: preview.srcset ?? null,
    displayWidth: preview.width ?? 0,
    displayHeight: preview.height ?? 0,
  };

  const thumbs: Record<string, ThumbState> = {};
  for (const [name, thumb] of Object.entries(payload.thumbs ?? {})) {
    thumbs[name] = thumbFromPayload(name, thumb);
  }

  const standalone = options.standalone ?? false;
  const sizes = options.sizes ?? payload.sizes ?? [];
  const crops: DialogState["crops"] = {};
  for (const size of sizes) {
    const name = typeof size.name === "string" ? size.name : "";
    if (!name) {
      continue;
    }
    const thumb = thumbForSize(thumbs, size, { standalone });
    const crop = thumb?.crop ?? null;
    crops[name] = {
      sourceId: PRIMARY_SOURCE_ID,
      box: crop && { x: crop.x, y: crop.y, w: crop.width, h: crop.height },
      changed: Boolean(crop) && !thumb?.id,
    };
  }

  return {
    phase: "crop",
    standalone,
    sources: { [PRIMARY_SOURCE_ID]: source },
    sizes,
    index: options.index ?? 0,
    crops,
    thumbs,
    warnings: (payload.warnings ?? []).map((warning) => ({
      code: warning.code ?? null,
      message: warning.message,
    })),
    error: null,
    errorCode: null,
    errorField: null,
    preview,
  };
}

/** One size's entry in a crop request. */
export interface CanonicalCropRequest {
  id: number | null;
  crop: PayloadCrop | null;
  width: number | null;
  height: number | null;
  changed: boolean;
  /** A rendition this session already made, which must not be copied over. */
  tmp: boolean;
  /** Reserved for per-crop override sources; null through 5.x. */
  source: string | null;
}

export interface CanonicalCropBody {
  image: {
    id: number | null;
    name: string;
    width: number | null;
    height: number | null;
  };
  sizes: Size[];
  standalone: boolean;
  /** Keyed by declared size name, every size, cropped or not. */
  thumbs: Record<string, CanonicalCropRequest>;
}

function sameBox(
  box: DialogState["crops"][string]["box"],
  crop: ThumbCrop | null,
): boolean {
  if (!box || !crop) {
    return !box && !crop;
  }
  return (
    box.x === crop.x &&
    box.y === crop.y &&
    box.w === crop.width &&
    box.h === crop.height
  );
}

/**
 * Whether a size has to be rendered again.
 *
 * Render again if the editor changed the box, it differs from the stored crop,
 * or no rendered crop exists.
 */
function cropChanged(
  entry: CropEntry | undefined,
  thumb: ThumbState | null,
): boolean {
  const box = entry?.box ?? null;
  if (!box) {
    return false;
  }
  return Boolean(entry?.changed) || !thumb?.id || !sameBox(box, thumb.crop);
}

/**
 * The body of `POST api/v1/crop/`.
 *
 * Include every declared size. The server returns a suggested box for a size
 * without one.
 */
export function stateToCanonicalCropBody(
  state: DialogState,
): CanonicalCropBody {
  const source =
    state.sources[PRIMARY_SOURCE_ID] ?? Object.values(state.sources)[0] ?? null;

  const thumbs: Record<string, CanonicalCropRequest> = {};
  for (const size of state.sizes) {
    const name = typeof size.name === "string" ? size.name : "";
    if (!name) {
      continue;
    }
    const entry = state.crops[name];
    const thumb = thumbForSize(state.thumbs, size, {
      standalone: state.standalone,
    });
    const box = entry?.box ?? null;
    thumbs[name] = {
      id: thumb?.id ?? null,
      crop: box && { x: box.x, y: box.y, width: box.w, height: box.h },
      width: thumb?.width || null,
      height: thumb?.height || null,
      changed: cropChanged(entry, thumb),
      tmp: Boolean(thumb?.tmp),
      source: null,
    };
  }

  return {
    image: {
      id: source?.imageId ?? null,
      name: source?.name ?? "",
      width: source?.width || null,
      height: source?.height || null,
    },
    sizes: state.sizes,
    standalone: state.standalone,
    thumbs,
  };
}

/**
 * `_tmp` dropped from a rendition's URL.
 *
 * The legacy crop response reports a crop twice: under `crop.thumbs` as the
 * file that exists right now, which is the temporary one until the form the
 * widget is on is saved, and on the crop's own entry as the file it will be
 * once it is. `payload_to_legacy` builds the second by asking storage for the
 * non-temporary name; this side derives it from the first by taking the suffix
 * off.
 */
function permanentUrl(url: string): string {
  return url.replace(/_tmp(?=(\.[^./?#]+)?([?#]|$))/, "");
}

/**
 * Return the storage URL expected by 4.x consumers, not the renderer URL.
 * Older v1 responses lack `file_url`, so cache-busted URLs fall back to their
 * path without the query string.
 */
function fileUrlOf(thumb: ThumbState): string | null {
  if (thumb.fileUrl) {
    return thumb.fileUrl;
  }
  return thumb.url === null ? null : withoutQuery(thumb.url);
}

function withoutQuery(url: string): string {
  return url.replace(/[?#].*$/, "");
}

function legacyThumb(thumb: ThumbState): LegacyThumb {
  const url = fileUrlOf(thumb);
  return {
    id: thumb.id,
    name: thumb.name,
    width: thumb.width,
    height: thumb.height,
    ...(url === null ? {} : { url }),
  };
}

/**
 * The preview bounding box the legacy payload's dimensions are reported
 * against: `CROPDUSTER_PREVIEW_WIDTH`/`CROPDUSTER_PREVIEW_HEIGHT`, whose
 * defaults these are. `_legacy_preview_size` reads the setting rather than the
 * `preview_size` the dialog was opened with, so this is not `previewSize`.
 */
const LEGACY_PREVIEW_BOUNDS = DEFAULT_PREVIEW_SIZE;

/**
 * Return the historical `preview_w` and `preview_h` values.
 *
 * Small images report the configured bounds rather than the preview file's
 * dimensions, matching both 4.x completion and a fresh page render. Crop
 * coordinates are scaled from the displayed image instead.
 */
function legacyPreviewSize(source: SourceImage | null): {
  preview_w: number;
  preview_h: number;
} {
  const [boundsW, boundsH] = LEGACY_PREVIEW_BOUNDS;
  const bounds = { preview_w: boundsW, preview_h: boundsH };
  const width = source?.width ?? 0;
  const height = source?.height ?? 0;
  if (!width || !height) {
    return bounds;
  }
  const ratio = Math.min(boundsW / width, boundsH / height);
  if (ratio >= 1) {
    return bounds;
  }
  return {
    preview_w: Math.round(width * ratio),
    preview_h: Math.round(height * ratio),
  };
}

/**
 * Build the 4.x completion object consumed by `CropDuster.complete()` and
 * CKEditor.
 *
 * The top-level `thumbs` list retains one entry per declared size for CKEditor.
 * `crop.thumbs` contains every rendered crop, including auto renditions, for
 * rebuilding the widget's select.
 */
export function stateToLegacyComplete(
  state: DialogState & { preview?: PayloadPreview | null },
): LegacyCompletePayload {
  const source =
    state.sources[PRIMARY_SOURCE_ID] ?? Object.values(state.sources)[0] ?? null;
  const preview = state.preview ?? null;

  const thumbs: Record<string, LegacyThumb> = {};
  for (const thumb of Object.values(state.thumbs)) {
    if (thumb.id === null) {
      // A box the server suggested but never rendered has no file to name.
      continue;
    }
    thumbs[thumb.name] = legacyThumb(thumb);
  }

  const forms: LegacyThumbForm[] = state.sizes.map((size) => {
    const name = typeof size.name === "string" ? size.name : "";
    const thumb = thumbForSize(state.thumbs, size, {
      standalone: state.standalone,
    });
    const stored = thumb?.crop;
    const box =
      state.crops[name]?.box ??
      (stored
        ? { x: stored.x, y: stored.y, w: stored.width, h: stored.height }
        : null);
    const file = thumb?.id ? fileUrlOf(thumb) : null;
    const url = file === null ? null : thumb?.tmp ? permanentUrl(file) : file;
    return {
      id: thumb?.id ?? null,
      name: thumb?.name || name,
      width: thumb?.width ?? null,
      height: thumb?.height ?? null,
      crop_x: box?.x ?? null,
      crop_y: box?.y ?? null,
      crop_w: box?.w ?? null,
      crop_h: box?.h ?? null,
      changed: Boolean(thumb?.id) || Boolean(state.crops[name]?.changed),
      size,
      thumbs: thumb?.id ? { [thumb.name]: legacyThumb(thumb) } : {},
      ...(url === null ? {} : { url }),
    };
  });

  return {
    crop: {
      image_id: source?.imageId ?? null,
      orig_image: source?.name ?? null,
      orig_w: source?.width ?? null,
      orig_h: source?.height ?? null,
      thumbs,
      standalone: state.standalone,
      sizes: state.sizes,
    },
    thumbs: forms,
    // The crop view hardcodes this.
    initial: true,
    // The preview rendition's file, which `payload_to_legacy` reports through
    // `_file_url` like every other URL here. Stripping the query string is the
    // fallback for a server that predates `preview.file_url`, exactly as in
    // `fileUrlOf`: it covers the cache-busting renderers and is all this side
    // can do for a renderer that answers on another host.
    preview_url:
      preview?.file_url ??
      withoutQuery(preview?.url ?? source?.displayUrl ?? ""),
    ...legacyPreviewSize(source),
  };
}
