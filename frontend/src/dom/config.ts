/**
 * Parse the JSON configuration on `<cropduster-widget>`.
 *
 * The configuration cannot contain values derived from a formset prefix:
 * django-nested-admin does not rewrite this element when it renames a cloned
 * row. Missing fields fall back independently for older or overridden markup.
 */

import type { Size } from "../crop/geometry";

export type DialogMode = "auto" | "modal" | "window";

export interface WidgetUrls {
  index: string | null;
  upload: string | null;
  crop: string | null;
  /** Null when the project routes 4.x's three views without the API. */
  api: string | null;
}

export interface WidgetPreviewConfig {
  url: string;
  rendererUrl: string | null;
  srcset: string | null;
  w: number | null;
  h: number | null;
}

export interface WidgetLabels {
  upload: string;
  /** The widget button once an image exists, when it opens the crop stage. */
  edit: string;
  cropContinue: string;
  cropGenerate: string;
  reupload: string;
}

export interface WidgetFeatures {
  /** Per-crop override sources are accepted by the API but not shown yet. */
  overrideSources: boolean;
}

/**
 * Identifies the model field being edited. The API uses it to load the size set
 * and upload directory from the model instead of accepting them from the
 * client. `objectId` is null until the object has been saved.
 */
export interface WidgetTarget {
  /** `app_label.modelname`, as `apps.get_model` takes it. */
  model: string;
  objectId: number | string | null;
  fieldName: string;
}

export interface WidgetConfig {
  /** Server-rendered sizes; current values are read from `data-sizes`. */
  sizes: Size[] | null;
  uploadTo: string;
  mediaUrl: string;
  fieldIdentifier: string;
  requireAltText: boolean;
  preview: WidgetPreviewConfig | null;
  urls: WidgetUrls;
  dialogMode: DialogMode;
  dispatchInputEvents: boolean;
  features: WidgetFeatures;
  /** Null for markup that predates the key, or a widget off any model field. */
  target: WidgetTarget | null;
  labels: WidgetLabels;
  csrfToken: string | null;
  debug: boolean;
}

export const DEFAULT_LABELS: WidgetLabels = {
  upload: "Upload Image",
  edit: "Edit Crops",
  cropContinue: "Crop and Continue",
  cropGenerate: "Crop and Generate Thumbs",
  reupload: "Re-Upload",
};

export const DEFAULT_CONFIG: WidgetConfig = {
  sizes: null,
  uploadTo: "",
  mediaUrl: "",
  fieldIdentifier: "",
  requireAltText: false,
  preview: null,
  urls: { index: null, upload: null, crop: null, api: null },
  dialogMode: "auto",
  dispatchInputEvents: true,
  features: { overrideSources: false },
  target: null,
  labels: DEFAULT_LABELS,
  csrfToken: null,
  debug: false,
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function str(value: unknown, fallback: string): string {
  return typeof value === "string" ? value : fallback;
}

function nullableStr(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function bool(value: unknown, fallback: boolean): boolean {
  return typeof value === "boolean" ? value : fallback;
}

function num(value: unknown): number | null {
  return typeof value === "number" && !Number.isNaN(value) ? value : null;
}

function dialogMode(value: unknown): DialogMode {
  return value === "modal" || value === "window" || value === "auto"
    ? value
    : DEFAULT_CONFIG.dialogMode;
}

function target(value: unknown): WidgetTarget | null {
  if (!isRecord(value)) {
    return null;
  }
  const model = str(value.model, "");
  const fieldName = str(value.fieldName, "");
  if (!model || !fieldName) {
    return null;
  }
  const objectId = value.objectId;
  return {
    model,
    fieldName,
    objectId:
      typeof objectId === "number" || typeof objectId === "string"
        ? objectId
        : null,
  };
}

function preview(value: unknown): WidgetPreviewConfig | null {
  if (!isRecord(value)) {
    return null;
  }
  return {
    url: str(value.url, ""),
    rendererUrl: nullableStr(value.rendererUrl),
    srcset: nullableStr(value.srcset),
    w: num(value.w),
    h: num(value.h),
  };
}

function urls(value: unknown): WidgetUrls {
  if (!isRecord(value)) {
    return { ...DEFAULT_CONFIG.urls };
  }
  return {
    index: nullableStr(value.index),
    upload: nullableStr(value.upload),
    crop: nullableStr(value.crop),
    api: nullableStr(value.api),
  };
}

/** Parse a `data-config` attribute, falling back to defaults field by field. */
export function parseConfig(raw: string | null | undefined): WidgetConfig {
  let parsed: unknown = null;
  if (raw) {
    try {
      parsed = JSON.parse(raw);
    } catch {
      parsed = null;
    }
  }
  if (!isRecord(parsed)) {
    return { ...DEFAULT_CONFIG, urls: { ...DEFAULT_CONFIG.urls } };
  }
  const features = isRecord(parsed.features) ? parsed.features : {};
  const labels = isRecord(parsed.labels) ? parsed.labels : {};
  return {
    sizes: Array.isArray(parsed.sizes) ? (parsed.sizes as Size[]) : null,
    uploadTo: str(parsed.uploadTo, DEFAULT_CONFIG.uploadTo),
    mediaUrl: str(parsed.mediaUrl, DEFAULT_CONFIG.mediaUrl),
    fieldIdentifier: str(
      parsed.fieldIdentifier,
      DEFAULT_CONFIG.fieldIdentifier,
    ),
    requireAltText: bool(parsed.requireAltText, DEFAULT_CONFIG.requireAltText),
    preview: preview(parsed.preview),
    urls: urls(parsed.urls),
    dialogMode: dialogMode(parsed.dialogMode),
    dispatchInputEvents: bool(
      parsed.dispatchInputEvents,
      DEFAULT_CONFIG.dispatchInputEvents,
    ),
    features: {
      overrideSources: bool(
        features.overrideSources,
        DEFAULT_CONFIG.features.overrideSources,
      ),
    },
    target: target(parsed.target),
    labels: {
      upload: str(labels.upload, DEFAULT_LABELS.upload),
      edit: str(labels.edit, DEFAULT_LABELS.edit),
      cropContinue: str(labels.cropContinue, DEFAULT_LABELS.cropContinue),
      cropGenerate: str(labels.cropGenerate, DEFAULT_LABELS.cropGenerate),
      reupload: str(labels.reupload, DEFAULT_LABELS.reupload),
    },
    csrfToken: nullableStr(parsed.csrfToken),
    debug: bool(parsed.debug, DEFAULT_CONFIG.debug),
  };
}

export function readConfig(el: Element): WidgetConfig {
  return parseConfig(el.getAttribute("data-config"));
}
