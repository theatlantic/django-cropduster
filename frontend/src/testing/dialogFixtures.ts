/** Test fixtures for the `dialog_config` rendered on `#cropduster-app`. */

import type { Size } from "../crop/geometry";
import type {
  CropDusterPayload,
  LegacyThumb,
  PayloadThumb,
} from "../formset/legacyPayload";
import { parseDialogConfig } from "../state/dialogConfig";
import type { DialogConfig } from "../state/dialogConfig";
import { payload as canonicalPayload, payloadThumb } from "./canonicalFixtures";

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
  thumbs?: Record<string, PayloadThumb>;
  cropThumbs?: Record<string, LegacyThumb>;
  /** Renderer-routed preview URL supplied by the page dialog. */
  previewRendererUrl?: string | null;
  previewSrcset?: string | null;
  legacyPreviewBounds?: readonly [number, number];
  initialState?: CropDusterPayload;
}

function thumb(
  name: string,
  options: {
    id?: number | null;
    width?: number | null;
    height?: number | null;
    crop?: { x: number; y: number; w: number; h: number } | null;
    url?: string | null;
  } = {},
): PayloadThumb {
  const crop = options.crop ?? null;
  const url = options.url ?? null;
  return payloadThumb(name, {
    id: options.id,
    width: options.width,
    height: options.height,
    crop: crop && { x: crop.x, y: crop.y, width: crop.w, height: crop.h },
    url,
    rendererUrl: url,
    fileUrl: url,
  });
}

function initialState(options: DialogConfigOptions): CropDusterPayload {
  if (options.initialState) {
    return options.initialState;
  }
  const sizes = options.sizes ?? [];
  const image = options.image ?? null;
  const thumbs = { ...(options.thumbs ?? {}) };
  for (const size of sizes) {
    const name = String(size.name);
    const crop = options.crops?.[name] ?? null;
    const saved = options.cropThumbs?.[name];
    if (crop || options.thumbIds?.[name] || saved) {
      thumbs[name] = thumb(name, {
        id: options.thumbIds?.[name] ?? saved?.id ?? null,
        width: saved?.width ?? null,
        height: saved?.height ?? null,
        crop,
        url: typeof saved?.url === "string" ? saved.url : null,
      });
    }
  }
  for (const [name, saved] of Object.entries(options.cropThumbs ?? {})) {
    thumbs[name] ??= thumb(name, {
      id: saved.id,
      width: saved.width,
      height: saved.height,
      url: typeof saved.url === "string" ? saved.url : null,
    });
  }
  const previewFile = image ? "/media/preview.jpg" : null;
  return canonicalPayload({
    image: image
      ? {
          ...image,
          url: `/media/${image.name}`,
        }
      : null,
    preview: {
      url: options.previewRendererUrl ?? previewFile,
      file_url: previewFile,
      srcset: options.previewSrcset ?? null,
      width: 800,
      height: 500,
    },
    sizes,
    thumbs,
  });
}

/** Serialize a `dialog_config` value for `data-config`. */
export function dialogConfigJson(options: DialogConfigOptions = {}): string {
  return JSON.stringify({
    elId: options.elId === undefined ? "lead_image" : options.elId,
    callbackFn: options.callbackFn ?? null,
    standalone: options.standalone ?? false,
    previewSize: { w: 800, h: 500 },
    legacyPreviewBounds: {
      w: options.legacyPreviewBounds?.[0] ?? 800,
      h: options.legacyPreviewBounds?.[1] ?? 500,
    },
    uploadTo: options.uploadTo ?? "article/lead_image/%Y/%m",
    urls: { api: "/cropduster/api/v1/" },
    initialState: initialState(options),
  });
}

export function dialogConfig(options: DialogConfigOptions = {}): DialogConfig {
  return parseDialogConfig(dialogConfigJson(options));
}
