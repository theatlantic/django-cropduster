/**
 * Parse the initial dialog state rendered by `CropDusterIndex`.
 *
 * Missing fields fall back to the 4.x query parameters so older or overridden
 * templates still open the upload step.
 */

import type { Size } from "../crop/geometry";
import type { WidgetTarget } from "../dom/config";
import type { LegacyThumb } from "../formset/legacyPayload";

/** Default preview bounds used by `store_upload`. */
export const DEFAULT_PREVIEW_SIZE: [number, number] = [800, 500];

export interface DialogImageConfig {
  id: number | null;
  name: string;
  url: string | null;
  width: number;
  height: number;
}

/** One crop step, index-aligned with `sizes`. */
export interface DialogThumbConfig {
  id: number | null;
  name: string;
  width: number | null;
  height: number | null;
  crop_x: number | null;
  crop_y: number | null;
  crop_w: number | null;
  crop_h: number | null;
  size: Size | null;
  /** The crop and the renditions that follow it, as `thumbs-N-thumbs`. */
  thumbs: Record<string, LegacyThumb>;
  changed: boolean;
  /** Stored-file URL retained for legacy completion. */
  url: string | null;
  rendererUrl: string | null;
  srcset: string | null;
}

export interface DialogPreviewConfig {
  /** Stored-file URL retained for legacy completion. */
  url: string;
  rendererUrl?: string | null;
  srcset?: string | null;
  w: number;
  h: number;
}

export interface DialogUrls {
  index: string | null;
  upload: string;
  crop: string;
  api: string | null;
}

/** Parameters for loading an existing image from `POST api/v1/state/`. */
export type DialogHydrateParams = Record<string, string>;

export interface DialogConfig {
  /** Field name returned unchanged on completion. */
  elId: string | null;
  /** CKEditor callback: `parent[callbackFn](callbackFn, payload)`. */
  callbackFn: string | null;
  standalone: boolean;
  maxW: number | null;
  sizes: Size[];
  /** Null until something is uploaded. */
  image: DialogImageConfig | null;
  thumbs: DialogThumbConfig[];
  /** Existing crops and their renditions from `crop-thumbs`. */
  cropThumbs: Record<string, LegacyThumb>;
  preview: DialogPreviewConfig;
  /** Preview bounds for uploads; null dimensions use server defaults. */
  previewSize: [number | null, number | null];
  minSize: { w: number; h: number };
  uploadTo: string;
  mediaUrl: string;
  urls: DialogUrls;
  /** CSRF token; `api/v1.ts` also checks the cookie and form input. */
  csrfToken: string | null;
  hydrate: DialogHydrateParams | null;
  /**
   * Identifies the field whose sizes and upload path the API resolves. Page
   * dialogs have no target and submit those values directly.
   */
  target: WidgetTarget | null;
  debug: boolean;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function str(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function nullableStr(value: unknown): string | null {
  return typeof value === "string" && value ? value : null;
}

function bool(value: unknown, fallback = false): boolean {
  return typeof value === "boolean" ? value : fallback;
}

function int(value: unknown, fallback = 0): number {
  if (typeof value === "number" && !Number.isNaN(value)) {
    return value;
  }
  if (typeof value === "string") {
    const parsed = parseInt(value, 10);
    if (!Number.isNaN(parsed)) {
      return parsed;
    }
  }
  return fallback;
}

function nullableInt(value: unknown): number | null {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const parsed = int(value, Number.NaN);
  return Number.isNaN(parsed) ? null : parsed;
}

function sizeList(value: unknown): Size[] {
  return Array.isArray(value) ? (value as Size[]) : [];
}

function thumbMap(value: unknown): Record<string, LegacyThumb> {
  if (!isRecord(value)) {
    return {};
  }
  const thumbs: Record<string, LegacyThumb> = {};
  for (const [name, entry] of Object.entries(value)) {
    if (isRecord(entry)) {
      thumbs[name] = entry as unknown as LegacyThumb;
    }
  }
  return thumbs;
}

/** Parse a query using 4.x's split-then-decode behavior. */
export function parseQuery(search: string): Record<string, string> {
  const params: Record<string, string> = {};
  for (const part of search.replace(/^\?/, "").split("&")) {
    if (!part) {
      continue;
    }
    const splits = part.split("=");
    if (splits.length <= 2) {
      params[splits[0] ?? ""] = decodeURIComponent(splits[1] ?? "");
    }
  }
  return params;
}

function parsePreviewSize(value: unknown): [number, number] | null {
  if (typeof value === "string") {
    const parts = value.split("x");
    if (parts.length === 2) {
      const w = parseInt(parts[0] ?? "", 10);
      const h = parseInt(parts[1] ?? "", 10);
      if (!Number.isNaN(w) && !Number.isNaN(h)) {
        return [w, h];
      }
    }
    return null;
  }
  if (Array.isArray(value) && value.length === 2) {
    return [int(value[0]), int(value[1])];
  }
  if (isRecord(value)) {
    return [int(value.w), int(value.h)];
  }
  return null;
}

function image(value: unknown): DialogImageConfig | null {
  if (!isRecord(value)) {
    return null;
  }
  const name = str(value.name);
  if (!name) {
    return null;
  }
  return {
    id: nullableInt(value.id),
    name,
    url: nullableStr(value.url),
    width: int(value.width),
    height: int(value.height),
  };
}

function thumbs(value: unknown): DialogThumbConfig[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter(isRecord).map((entry) => ({
    id: nullableInt(entry.id),
    name: str(entry.name),
    width: nullableInt(entry.width),
    height: nullableInt(entry.height),
    crop_x: nullableInt(entry.crop_x),
    crop_y: nullableInt(entry.crop_y),
    crop_w: nullableInt(entry.crop_w),
    crop_h: nullableInt(entry.crop_h),
    size: isRecord(entry.size) ? (entry.size as Size) : null,
    thumbs: thumbMap(entry.thumbs),
    changed: bool(entry.changed),
    url: nullableStr(entry.url),
    rendererUrl:
      nullableStr(entry.renderer_url) ?? nullableStr(entry.rendererUrl),
    srcset: nullableStr(entry.srcset),
  }));
}

/** Read configured endpoints, falling back to paths beside the dialog URL. */
function urls(value: unknown, pathname: string): DialogUrls {
  const config = isRecord(value) ? value : {};
  const base = pathname.replace(/standalone\/$/, "");
  return {
    index: nullableStr(config.index),
    upload: nullableStr(config.upload) ?? `${base}upload/`,
    crop: nullableStr(config.crop) ?? `${base}crop/`,
    api: nullableStr(config.api),
  };
}

/** Create empty crop steps when the config supplies none. */
function thumbsFromSizes(sizes: Size[]): DialogThumbConfig[] {
  return sizes.map((size) => ({
    id: null,
    name: str(size.name),
    width: null,
    height: null,
    crop_x: null,
    crop_y: null,
    crop_w: null,
    crop_h: null,
    size,
    thumbs: {},
    changed: false,
    url: null,
    rendererUrl: null,
    srcset: null,
  }));
}

export interface ReadConfigOptions {
  /** `location.search`; the fallback for anything the config omits. */
  search?: string;
  /** `location.pathname`; where the endpoint fallbacks are derived from. */
  pathname?: string;
}

export function parseDialogConfig(
  raw: string | null | undefined,
  options: ReadConfigOptions = {},
): DialogConfig {
  let parsed: unknown = null;
  if (raw) {
    try {
      parsed = JSON.parse(raw);
    } catch {
      parsed = null;
    }
  }
  const config = isRecord(parsed) ? parsed : {};
  const query = parseQuery(options.search ?? "");
  const pathname = options.pathname ?? "/cropduster/";

  let sizes = sizeList(config.sizes);
  if (!sizes.length && query.sizes) {
    try {
      sizes = sizeList(JSON.parse(query.sizes));
    } catch {
      sizes = [];
    }
  }

  const configured = thumbs(config.thumbs);
  const preview = isRecord(config.preview) ? config.preview : {};

  return {
    elId: nullableStr(config.elId) ?? (query.el_id || null),
    callbackFn: nullableStr(config.callbackFn) ?? (query.callback_fn || null),
    standalone: bool(config.standalone, /standalone\/$/.test(pathname)),
    maxW: nullableInt(config.maxW) ?? nullableInt(query.max_w),
    sizes,
    image: image(config.image),
    thumbs: configured.length ? configured : thumbsFromSizes(sizes),
    cropThumbs: thumbMap(config.cropThumbs),
    preview: {
      url: str(preview.url),
      rendererUrl: nullableStr(preview.rendererUrl),
      srcset: nullableStr(preview.srcset),
      w: int(preview.w),
      h: int(preview.h),
    },
    previewSize:
      parsePreviewSize(config.previewSize) ??
      parsePreviewSize(query.preview_size) ??
      // Without an image, the preview dimensions are already the bounds.
      (config.image ? DEFAULT_PREVIEW_SIZE : [int(preview.w), int(preview.h)]),
    minSize: {
      w: int(isRecord(config.minSize) ? config.minSize.w : 0),
      h: int(isRecord(config.minSize) ? config.minSize.h : 0),
    },
    uploadTo: str(config.uploadTo) || str(query.upload_to),
    mediaUrl: str(config.mediaUrl),
    urls: urls(config.urls, pathname),
    csrfToken: nullableStr(config.csrfToken),
    // The page dialog is served with its state already resolved.
    hydrate: null,
    target: null,
    debug: bool(config.debug, query.cropduster_debug === "1"),
  };
}

export function readDialogConfig(
  el: Element,
  options: ReadConfigOptions = {},
): DialogConfig {
  return parseDialogConfig(el.getAttribute("data-config"), options);
}
