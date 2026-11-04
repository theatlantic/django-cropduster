/**
 * Unhashed class names used by Cropduster, django-nested-admin, and downstream
 * stylesheets or scripts.
 */

/** The wrapper div, `id="{prefix}-group"`. nested-admin renames it by class. */
export const FORM = "cropduster-form";

/** `input[name="{prefix}"]`, which every prefix is derived from. */
export const DATA_FIELD = "cropduster-data-field";

export const TEXT_FIELD = "cropduster-text-field";

/** The anchor React portals the upload button into. */
export const CUSTOM_FIELD = "cropduster-customfield";

export const UPLOAD_FORM = "cropduster-upload-form";

export const BUTTON = "cropduster-button";

/**
 * Retained for downstream checks. Dialog buttons also use the `disabled`
 * attribute, which prevents clicks and removes them from the tab order.
 */
export const DISABLED = "disabled";

/** The div React portals thumbnails into. */
export const IMAGES = "cropduster-images";

export const THUMBS = "thumbs";

/** One rendered thumbnail anchor; suffixed with the size slug. */
export const IMAGE = "cropduster-image";

/** The img inside it; suffixed with the size slug. */
export const IMAGE_THUMB = "cropduster-image-thumb";

/** Toggled on the wrapper while the DELETE checkbox is checked. */
export const PREDELETE = "predelete";

/** Toggled on the wrapper while no image is stored; hides the text fields. */
export const NO_IMAGE = "cropduster-no-image";

/** grappelli's spelling of the same state. */
export const GRP_PREDELETE = "grp-predelete";

/** Set on `<body>` by `?cropduster_debug=1` to unhide the raw formset rows. */
export const DEBUG_BODY = "cropduster-debug";

export const WIDGET_TAG = "cropduster-widget";

/** The size slug `createThumbnails` renders the preview under. */
export const PREVIEW_SLUG = "preview";

export const SELECTORS = {
  form: `.${FORM}`,
  dataField: `.${DATA_FIELD}`,
  customField: `.${CUSTOM_FIELD}`,
  images: `.${IMAGES}`,
  widget: WIDGET_TAG,
  /** The row the 4.x upload handler resolves its data field through. */
  row: ".form-row,.row,.grp-row",
} as const;
