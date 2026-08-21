/**
 * Build a modal's initial configuration from widget settings and current
 * formset values. Existing images include a state request for the original
 * dimensions and saved crop boxes that the formset does not contain.
 */

import {
  emptyInitialState,
  type DialogConfig,
  type DialogHydrateParams,
} from "./dialogConfig";
import type { Size } from "../crop/geometry";
import type { WidgetConfig } from "../dom/config";
import type { FormsetBridge, WidgetState } from "../formset/FormsetBridge";
import type { CropDusterPayload } from "../formset/legacyPayload";
import { readData } from "../dom/jquery";

export interface DialogSource {
  bridge: FormsetBridge;
  config: WidgetConfig;
}

function toNumber(value: string): number | null {
  const parsed = parseInt(value, 10);
  return Number.isNaN(parsed) ? null : parsed;
}

/** Return `POST api/v1/state/` parameters for a widget with an image. */
export function hydrateParams(
  widget: DialogSource,
  state: WidgetState = widget.bridge.readState(),
  sizes?: Size[],
): DialogHydrateParams | null {
  if (!state.origImage) {
    return null;
  }
  const params: DialogHydrateParams = {
    image: state.origImage,
    sizes: JSON.stringify(sizes ?? widget.bridge.readSizes()),
  };
  if (state.imageId) {
    params.id = state.imageId;
  }
  const uploadTo = uploadToOf(widget);
  if (uploadTo) {
    params.upload_to = uploadTo;
  }
  // Read crops from the bound formset rather than the image while editing.
  const thumbIds = state.thumbs.map((thumb) => thumb.id).filter(Boolean);
  if (thumbIds.length) {
    params.thumbs = thumbIds.join(",");
  }
  const tmpThumbIds = state.thumbs
    .filter((thumb) => thumb.tmp)
    .map((thumb) => thumb.id)
    .filter(Boolean);
  if (tmpThumbIds.length) {
    params.tmp_thumbs = tmpThumbIds.join(",");
  }
  return params;
}

function uploadToOf(widget: DialogSource): string {
  const fromDom = readData(widget.bridge.dataField, "uploadTo");
  return typeof fromDom === "string" && fromDom
    ? fromDom
    : widget.config.uploadTo;
}

function initialState(state: WidgetState, sizes: Size[]): CropDusterPayload {
  return {
    ...emptyInitialState(sizes),
    image: state.origImage
      ? {
          id: toNumber(state.imageId),
          name: state.origImage,
          url: null,
          width: null,
          height: null,
          field_identifier: "",
          content_type_id: null,
          object_id: null,
        }
      : null,
    preview: {
      url: state.preview.rendererUrl || state.preview.url || null,
      file_url: state.preview.url || null,
      srcset: state.preview.srcset || null,
      width: toNumber(state.preview.width),
      height: toNumber(state.preview.height),
    },
  };
}

/**
 * Build modal configuration. `elId` retains the current prefix for the 4.x
 * completion object; the modal writes through the widget element itself.
 */
export function dialogConfigForWidget(widget: DialogSource): DialogConfig {
  const { bridge, config } = widget;
  const state = bridge.readState();
  const sizes = bridge.readSizes();

  return {
    elId: state.prefix,
    callbackFn: null,
    standalone: false,
    initialState: initialState(state, sizes),
    // The server's own bounds, rather than this widget's current preview.
    previewSize: [null, null],
    legacyPreviewBounds: config.legacyPreviewBounds,
    uploadTo: uploadToOf(widget),
    urls: { api: config.urls.api },
    csrfToken: config.csrfToken,
    hydrate: hydrateParams(widget, state, sizes),
    target: config.target,
  };
}
