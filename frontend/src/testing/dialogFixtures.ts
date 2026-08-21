/** Test fixtures for the `dialog_config` rendered on `#cropduster-app`. */

import type { Size } from "../crop/geometry";
import type { LegacyThumb } from "../formset/legacyPayload";
import { parseDialogConfig } from "../state/dialogConfig";
import type { DialogConfig, DialogThumbConfig } from "../state/dialogConfig";

export interface DialogConfigOptions {
  sizes?: Size[];
  standalone?: boolean;
  elId?: string | null;
  callbackFn?: string | null;
  uploadTo?: string;
  /** Existing image and dimensions rendered by the view. */
  image?: { id: number | null; name: string; width: number; height: number };
  crops?: Record<string, { x: number; y: number; w: number; h: number }>;
  thumbIds?: Record<string, number>;
  /** Optional crop steps from a recorded dialog state. */
  thumbs?: DialogThumbConfig[];
  cropThumbs?: Record<string, LegacyThumb>;
  /** Renderer-routed preview URL supplied by the page dialog. */
  previewRendererUrl?: string | null;
  previewSrcset?: string | null;
}

/** Serialize a `dialog_config` value for `data-config`. */
export function dialogConfigJson(options: DialogConfigOptions = {}): string {
  const sizes = options.sizes ?? [];
  const image = options.image ?? null;
  return JSON.stringify({
    elId: options.elId === undefined ? "lead_image" : options.elId,
    callbackFn: options.callbackFn ?? null,
    standalone: options.standalone ?? false,
    maxW: null,
    sizes,
    image: image && { ...image, url: `/media/${image.name}` },
    thumbs:
      options.thumbs ??
      sizes.map((size) => {
        const name = String(size.name);
        const crop = options.crops?.[name] ?? null;
        return {
          id: options.thumbIds?.[name] ?? null,
          name,
          width: null,
          height: null,
          crop_x: crop?.x ?? null,
          crop_y: crop?.y ?? null,
          crop_w: crop?.w ?? null,
          crop_h: crop?.h ?? null,
          size,
          thumbs: {},
          changed: false,
          url: null,
        };
      }),
    cropThumbs: options.cropThumbs ?? {},
    preview: {
      url: image ? "/media/preview.jpg" : "/static/cropduster/img/blank.gif",
      rendererUrl: options.previewRendererUrl ?? null,
      srcset: options.previewSrcset ?? null,
      w: 800,
      h: 500,
    },
    previewSize: { w: 800, h: 500 },
    minSize: { w: 0, h: 0 },
    uploadTo: options.uploadTo ?? "article/lead_image/%Y/%m",
    mediaUrl: "/media/",
    urls: {
      index: "/cropduster/",
      upload: "/cropduster/upload/",
      crop: "/cropduster/crop/",
      api: "/cropduster/api/v1/",
    },
    debug: false,
  });
}

export function dialogConfig(options: DialogConfigOptions = {}): DialogConfig {
  return parseDialogConfig(dialogConfigJson(options));
}
