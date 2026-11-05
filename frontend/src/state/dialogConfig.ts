/**
 * Parse the initial dialog state rendered by `CropDusterIndex`.
 *
 * Missing fields fall back to the 4.x query parameters so older or overridden
 * templates still open the upload step.
 */

import type { Size } from "../crop/geometry";
import type { WidgetTarget } from "../dom/config";
import type { CropDusterPayload } from "../formset/legacyPayload";

/** Default preview bounds used by `store_upload`. */
export const DEFAULT_PREVIEW_SIZE: [number, number] = [800, 500];

export interface DialogUrls {
  api: string | null;
}

/** Parameters for loading an existing image from `api/v1/state/`. */
export type DialogHydrateParams = Record<string, string>;

export interface DialogConfig {
  /** Field name returned unchanged on completion. */
  elId: string | null;
  /** CKEditor callback: `parent[callbackFn](callbackFn, payload)`. */
  callbackFn: string | null;
  standalone: boolean;
  /** The same versioned image state returned by the JSON API. */
  initialState: CropDusterPayload;
  /** Preview bounds for uploads; null dimensions use server defaults. */
  previewSize: [number | null, number | null];
  /** Project-wide bounds used by the 4.x completion payload. */
  legacyPreviewBounds: [number, number];
  uploadTo: string;
  urls: DialogUrls;
  /** CSRF token; `api/v1.ts` also checks the cookie and form input. */
  csrfToken: string | null;
  hydrate: DialogHydrateParams | null;
  /**
   * Identifies the field whose sizes and upload path the API resolves. Page
   * dialogs have no target and submit those values directly.
   */
  target: WidgetTarget | null;
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

function sizeList(value: unknown): Size[] {
  return Array.isArray(value) ? (value as Size[]) : [];
}

/** Return a v1 payload for a dialog that has no image yet. */
export function emptyInitialState(sizes: Size[]): CropDusterPayload {
  return {
    version: 1,
    image: null,
    preview: null,
    sizes,
    thumbs: {},
    metadata: {
      attribution: null,
      attribution_link: null,
      caption: null,
      alt_text: null,
    },
    warnings: [],
  };
}

/** Read the server-rendered v1 payload, or an empty 4.x-query fallback. */
function initialState(
  value: unknown,
  fallbackSizes: Size[],
): CropDusterPayload {
  if (
    !isRecord(value) ||
    value.version !== 1 ||
    !Array.isArray(value.sizes) ||
    !isRecord(value.thumbs)
  ) {
    return emptyInitialState(fallbackSizes);
  }
  return value as unknown as CropDusterPayload;
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

function urls(value: unknown): DialogUrls {
  const config = isRecord(value) ? value : {};
  return {
    api: nullableStr(config.api),
  };
}

export interface ReadConfigOptions {
  /** `location.search`; the fallback for anything the config omits. */
  search?: string;
  /** `location.pathname`; used to infer standalone mode as a fallback. */
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

  let fallbackSizes: Size[] = [];
  if (query.sizes) {
    try {
      fallbackSizes = sizeList(JSON.parse(query.sizes));
    } catch {
      fallbackSizes = [];
    }
  }
  const state = initialState(config.initialState, fallbackSizes);
  const preview = state.preview;

  return {
    elId: nullableStr(config.elId) ?? (query.el_id || null),
    callbackFn: nullableStr(config.callbackFn) ?? (query.callback_fn || null),
    standalone: bool(config.standalone, /standalone\/$/.test(pathname)),
    initialState: state,
    previewSize:
      parsePreviewSize(config.previewSize) ??
      parsePreviewSize(query.preview_size) ??
      (state.image?.name
        ? DEFAULT_PREVIEW_SIZE
        : [int(preview?.width), int(preview?.height)]),
    legacyPreviewBounds: parsePreviewSize(config.legacyPreviewBounds) ?? [
      ...DEFAULT_PREVIEW_SIZE,
    ],
    uploadTo: str(config.uploadTo) || str(query.upload_to),
    urls: urls(config.urls),
    csrfToken: nullableStr(config.csrfToken),
    // The page dialog is served with its state already resolved.
    hydrate: null,
    target: null,
  };
}

export function readDialogConfig(
  el: Element,
  options: ReadConfigOptions = {},
): DialogConfig {
  return parseDialogConfig(el.getAttribute("data-config"), options);
}
