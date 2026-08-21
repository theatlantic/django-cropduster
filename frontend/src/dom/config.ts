/**
 * Parse the JSON configuration on `<cropduster-widget>`.
 *
 * The configuration cannot contain values derived from a formset prefix:
 * django-nested-admin does not rewrite this element when it renames a cloned
 * row. Missing fields fall back independently for older or overridden markup.
 */

export type DialogMode = "auto" | "modal" | "window";

export interface WidgetUrls {
  /** Null when the project routes 4.x's three views without the API. */
  api: string | null;
}

export interface WidgetLabels {
  upload: string;
  /** The widget button once an image exists, when it opens the crop stage. */
  edit: string;
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
  uploadTo: string;
  mediaUrl: string;
  /** Project-wide bounds used by the 4.x completion payload. */
  legacyPreviewBounds: [number, number];
  urls: WidgetUrls;
  dialogMode: DialogMode;
  dispatchInputEvents: boolean;
  /** Null for markup that predates the key, or a widget off any model field. */
  target: WidgetTarget | null;
  labels: WidgetLabels;
  csrfToken: string | null;
}

export const DEFAULT_LABELS: WidgetLabels = {
  upload: "Upload Image",
  edit: "Edit Crops",
};

export const DEFAULT_CONFIG: WidgetConfig = {
  uploadTo: "",
  mediaUrl: "",
  legacyPreviewBounds: [800, 500],
  urls: { api: null },
  dialogMode: "auto",
  dispatchInputEvents: true,
  target: null,
  labels: DEFAULT_LABELS,
  csrfToken: null,
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

function legacyPreviewBounds(value: unknown): [number, number] {
  const configured = isRecord(value) ? value : {};
  return [
    num(configured.w) ?? DEFAULT_CONFIG.legacyPreviewBounds[0],
    num(configured.h) ?? DEFAULT_CONFIG.legacyPreviewBounds[1],
  ];
}

function urls(value: unknown): WidgetUrls {
  if (!isRecord(value)) {
    return { ...DEFAULT_CONFIG.urls };
  }
  return {
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
    return {
      ...DEFAULT_CONFIG,
      legacyPreviewBounds: [...DEFAULT_CONFIG.legacyPreviewBounds],
      urls: { ...DEFAULT_CONFIG.urls },
    };
  }
  const labels = isRecord(parsed.labels) ? parsed.labels : {};
  return {
    uploadTo: str(parsed.uploadTo, DEFAULT_CONFIG.uploadTo),
    mediaUrl: str(parsed.mediaUrl, DEFAULT_CONFIG.mediaUrl),
    legacyPreviewBounds: legacyPreviewBounds(parsed.legacyPreviewBounds),
    urls: urls(parsed.urls),
    dialogMode: dialogMode(parsed.dialogMode),
    dispatchInputEvents: bool(
      parsed.dispatchInputEvents,
      DEFAULT_CONFIG.dispatchInputEvents,
    ),
    target: target(parsed.target),
    labels: {
      upload: str(labels.upload, DEFAULT_LABELS.upload),
      edit: str(labels.edit, DEFAULT_LABELS.edit),
    },
    csrfToken: nullableStr(parsed.csrfToken),
  };
}

export function readConfig(el: Element): WidgetConfig {
  return parseConfig(el.getAttribute("data-config"));
}
