/**
 * Build a modal's initial configuration from widget settings and current
 * formset values. Existing images include a state request for the original
 * dimensions and saved crop boxes that the formset does not contain.
 */

import type { DialogConfig, DialogHydrateParams } from "./dialogConfig";
import type { WidgetConfig } from "../dom/config";
import type { FormsetBridge } from "../formset/FormsetBridge";
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
): DialogHydrateParams | null {
  const state = widget.bridge.readState();
  if (!state.origImage) {
    return null;
  }
  const params: DialogHydrateParams = {
    image: state.origImage,
    sizes: JSON.stringify(widget.bridge.readSizes()),
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
  return params;
}

function uploadToOf(widget: DialogSource): string {
  const fromDom = readData(widget.bridge.dataField, "uploadTo");
  return typeof fromDom === "string" && fromDom
    ? fromDom
    : widget.config.uploadTo;
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
    maxW: null,
    sizes,
    image: state.origImage
      ? {
          id: toNumber(state.imageId),
          name: state.origImage,
          url: null,
          // Filled in by the state request; the formset has neither.
          width: 0,
          height: 0,
        }
      : null,
    thumbs: [],
    cropThumbs: {},
    preview: {
      url: state.preview.url,
      rendererUrl: state.preview.rendererUrl || null,
      srcset: state.preview.srcset || null,
      w: toNumber(state.preview.width) ?? 0,
      h: toNumber(state.preview.height) ?? 0,
    },
    // The server's own bounds, rather than this widget's current preview.
    previewSize: [null, null],
    minSize: { w: 0, h: 0 },
    uploadTo: uploadToOf(widget),
    mediaUrl: bridge.mediaUrl || config.mediaUrl,
    urls: {
      index: config.urls.index,
      upload: config.urls.upload ?? "",
      crop: config.urls.crop ?? "",
      api: config.urls.api,
    },
    csrfToken: config.csrfToken,
    hydrate: hydrateParams(widget),
    target: config.target,
    debug: config.debug,
  };
}
