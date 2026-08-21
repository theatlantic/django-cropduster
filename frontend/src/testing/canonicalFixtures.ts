/**
 * v1 response fixtures corresponding to recorded 4.15 upload and crop cases.
 * `{Y}/{m}` and `{DIR}` replace date- and run-specific path segments; size
 * definitions are loaded from the recordings.
 */

import type {
  CropDusterPayload,
  PayloadCrop,
  PayloadImage,
  PayloadPreview,
  PayloadThumb,
  PayloadWarning,
} from "../formset/legacyPayload";
import type { Size } from "../crop/geometry";
import { cropFixture } from "./legacyWire";

/** Load the size list sent by a recorded 4.x crop request. */
function recordedSizes(name: string): Size[] {
  const fixture = cropFixture(name);
  return JSON.parse(fixture.request.post["crop-sizes"] ?? "[]") as Size[];
}

/** `tests.models.Author.headshot`: main 220x180 with an auto thumb 110x90. */
export const HEADSHOT_SIZES = recordedSizes("crop_author_headshot");

/** `tests.models.Article.lead_image`: main 600x480 + auto, no_height w=600. */
export const LEAD_IMAGE_SIZES = recordedSizes("crop_lead_image_suggest");

/** The standalone (CKEditor) size set: one free-form crop. */
export const STANDALONE_SIZES = recordedSizes("standalone_crop");

export const HEADSHOT_DIR = "author/headshots/{Y}/{m}/{DIR}";
export const LEAD_IMAGE_DIR = "article/lead_image/{Y}/{m}/{DIR}";
export const STANDALONE_DIR = "img/posts/{Y}/{m}/{DIR}";

/**
 * Query appended by `FileRenderer`. Fixtures include renderer and storage URLs
 * because the 4.x completion payload returns storage URLs.
 */
export const CACHE_BUSTER = "?mod=1755000000";

export const THUMBOR_SOURCE_WIDTH = 1684;
export const THUMBOR_SOURCE_HEIGHT = 2000;
export const THUMBOR_MAIN_CROP = {
  x: 0,
  y: 311,
  width: 1684,
  height: 1378,
};
export const THUMBOR_PREVIEW_1X = `https://thumbor.example.com/unsafe/fit-in/800x500/media/${HEADSHOT_DIR}/original.jpg`;
export const THUMBOR_PREVIEW_2X = `https://thumbor.example.com/unsafe/fit-in/1600x1000/media/${HEADSHOT_DIR}/original.jpg`;
export const THUMBOR_PREVIEW_SRCSET = `${THUMBOR_PREVIEW_2X} 2x`;

export const THUMBOR_MAIN_1X = `https://thumbor.example.com/unsafe/0x311:1684x1689/220x180/media/${HEADSHOT_DIR}/original.jpg`;
export const THUMBOR_MAIN_2X = `https://thumbor.example.com/unsafe/0x311:1684x1689/440x360/media/${HEADSHOT_DIR}/original.jpg`;
export const THUMBOR_MAIN_SRCSET = `${THUMBOR_MAIN_1X}, ${THUMBOR_MAIN_2X} 2x`;
export const THUMBOR_AUTO_1X = `https://thumbor.example.com/unsafe/0x311:1684x1689/110x90/media/${HEADSHOT_DIR}/original.jpg`;
export const THUMBOR_AUTO_2X = `https://thumbor.example.com/unsafe/0x311:1684x1689/220x180/media/${HEADSHOT_DIR}/original.jpg`;
export const THUMBOR_AUTO_SRCSET = `${THUMBOR_AUTO_1X}, ${THUMBOR_AUTO_2X} 2x`;

export interface ThumbOptions {
  id?: number | null;
  width?: number | null;
  height?: number | null;
  crop?: PayloadCrop | null;
  ref?: string | null;
  refId?: number | null;
  /** Storage URL used to derive the cache-busted renderer URL. */
  url?: string | null;
  /** Explicit renderer URL for a backend that does not serve the stored file. */
  rendererUrl?: string | null;
  /** Explicit `file_url`; null simulates an older v1 response. */
  fileUrl?: string | null;
  srcset?: string | null;
  tmp?: boolean;
  changed?: boolean;
}

export function payloadThumb(
  name: string,
  options: ThumbOptions = {},
): PayloadThumb {
  const file = options.url ?? null;
  return {
    id: options.id ?? null,
    name,
    width: options.width ?? null,
    height: options.height ?? null,
    crop: options.crop ?? null,
    ref: options.ref ?? null,
    ref_id: options.refId ?? null,
    url:
      options.rendererUrl === undefined
        ? file === null
          ? null
          : `${file}${CACHE_BUSTER}`
        : options.rendererUrl,
    file_url: options.fileUrl === undefined ? file : options.fileUrl,
    srcset: options.srcset ?? null,
    tmp: options.tmp ?? false,
    changed: options.changed ?? false,
    source: null,
  };
}

export interface PayloadOptions {
  image?: Partial<PayloadImage> | null;
  preview?: Partial<PayloadPreview> | null;
  sizes?: Size[];
  thumbs?: Record<string, PayloadThumb>;
  warnings?: PayloadWarning[];
}

export function payload(options: PayloadOptions = {}): CropDusterPayload {
  return {
    version: 1,
    image:
      options.image === null
        ? null
        : {
            id: null,
            name: "",
            url: null,
            width: null,
            height: null,
            field_identifier: "",
            content_type_id: null,
            object_id: null,
            ...options.image,
          },
    preview:
      options.preview === null
        ? null
        : {
            url: null,
            srcset: null,
            width: null,
            height: null,
            file_url: null,
            ...options.preview,
          },
    sizes: options.sizes ?? [],
    thumbs: options.thumbs ?? {},
    metadata: {
      attribution: null,
      attribution_link: null,
      caption: null,
      alt_text: null,
    },
    warnings: options.warnings ?? [],
  };
}

/** v1 upload response for `tests/data/img.jpg` (674x800) and `headshot`. */
export function headshotUpload(
  overrides: PayloadOptions = {},
): CropDusterPayload {
  return payload({
    image: {
      id: null,
      name: `${HEADSHOT_DIR}/original.jpg`,
      url: `/media/${HEADSHOT_DIR}/original.jpg${CACHE_BUSTER}`,
      width: 674,
      height: 800,
    },
    preview: {
      url: `/media/${HEADSHOT_DIR}/_preview.jpg${CACHE_BUSTER}`,
      file_url: `/media/${HEADSHOT_DIR}/_preview.jpg`,
      width: 421,
      height: 500,
    },
    sizes: HEADSHOT_SIZES,
    ...overrides,
  });
}

/** v1 crop response for a centered headshot, including `main`'s auto child. */
export function headshotCrop(
  overrides: PayloadOptions = {},
): CropDusterPayload {
  return headshotUpload({
    thumbs: {
      main: payloadThumb("main", {
        id: 1,
        width: 220,
        height: 180,
        crop: { x: 0, y: 125, width: 674, height: 551 },
        url: `/media/${HEADSHOT_DIR}/main_tmp.jpg`,
        tmp: true,
        changed: true,
      }),
      thumb: payloadThumb("thumb", {
        id: 2,
        width: 110,
        height: 90,
        ref: "main",
        refId: 1,
        url: `/media/${HEADSHOT_DIR}/thumb_tmp.jpg`,
        rendererUrl: THUMBOR_AUTO_1X,
        srcset: THUMBOR_AUTO_SRCSET,
        tmp: true,
        changed: true,
      }),
    },
    ...overrides,
  });
}

/** The same crop response with renderer-routed 1x and 2x candidates. */
export function thumborHeadshotCrop(
  overrides: PayloadOptions = {},
): CropDusterPayload {
  return headshotCrop({
    image: {
      id: null,
      name: `${HEADSHOT_DIR}/original.jpg`,
      url: `/media/${HEADSHOT_DIR}/original.jpg${CACHE_BUSTER}`,
      width: THUMBOR_SOURCE_WIDTH,
      height: THUMBOR_SOURCE_HEIGHT,
    },
    preview: {
      url: THUMBOR_PREVIEW_1X,
      srcset: THUMBOR_PREVIEW_SRCSET,
      file_url: `/media/${HEADSHOT_DIR}/_preview.jpg`,
      width: 421,
      height: 500,
    },
    thumbs: {
      main: payloadThumb("main", {
        id: 1,
        width: 220,
        height: 180,
        crop: THUMBOR_MAIN_CROP,
        url: `/media/${HEADSHOT_DIR}/main_tmp.jpg`,
        rendererUrl: THUMBOR_MAIN_1X,
        srcset: THUMBOR_MAIN_SRCSET,
        tmp: true,
        changed: true,
      }),
      thumb: payloadThumb("thumb", {
        id: 2,
        width: 110,
        height: 90,
        ref: "main",
        refId: 1,
        url: `/media/${HEADSHOT_DIR}/thumb_tmp.jpg`,
        tmp: true,
        changed: true,
      }),
    },
    ...overrides,
  });
}

/**
 * v1 crop response for `lead_image`, including `Size.fit_to_crop()`'s
 * suggestion for the unrendered `no_height` crop.
 */
export function leadImageSuggestion(
  overrides: PayloadOptions = {},
): CropDusterPayload {
  return payload({
    image: {
      id: null,
      name: `${LEAD_IMAGE_DIR}/original.jpg`,
      url: `/media/${LEAD_IMAGE_DIR}/original.jpg${CACHE_BUSTER}`,
      width: 1300,
      height: 1016,
    },
    preview: {
      url: `/media/${LEAD_IMAGE_DIR}/_preview.jpg${CACHE_BUSTER}`,
      file_url: `/media/${LEAD_IMAGE_DIR}/_preview.jpg`,
      width: 640,
      height: 500,
    },
    sizes: LEAD_IMAGE_SIZES,
    thumbs: {
      main: payloadThumb("main", {
        id: 1,
        width: 600,
        height: 480,
        crop: { x: 15, y: 0, width: 1270, height: 1016 },
        url: `/media/${LEAD_IMAGE_DIR}/main_tmp.jpg`,
        tmp: true,
        changed: true,
      }),
      thumb: payloadThumb("thumb", {
        id: 2,
        width: 110,
        height: 90,
        ref: "main",
        refId: 1,
        url: `/media/${LEAD_IMAGE_DIR}/thumb_tmp.jpg`,
        tmp: true,
        changed: true,
      }),
      // Suggested but not rendered, so it has no id or file.
      no_height: payloadThumb("no_height", {
        crop: { x: 15, y: 0, width: 1270, height: 1016 },
        changed: true,
      }),
    },
    ...overrides,
  });
}

/** v1 standalone upload response; the crop name is a digest, not a size. */
export function standaloneUpload(
  overrides: PayloadOptions = {},
): CropDusterPayload {
  return payload({
    image: {
      id: 1,
      name: `${STANDALONE_DIR}/original.jpg`,
      url: `/media/${STANDALONE_DIR}/original.jpg${CACHE_BUSTER}`,
      width: 674,
      height: 800,
    },
    preview: {
      url: `/media/${STANDALONE_DIR}/_preview.jpg${CACHE_BUSTER}`,
      file_url: `/media/${STANDALONE_DIR}/_preview.jpg`,
      width: 421,
      height: 500,
    },
    sizes: STANDALONE_SIZES,
    thumbs: {
      "0e4ab476e": payloadThumb("0e4ab476e", {
        id: 1,
        width: 674,
        height: 800,
        crop: { x: 0, y: 0, width: 674, height: 800 },
        url: `/media/${STANDALONE_DIR}/0e4ab476e.jpg`,
      }),
    },
    ...overrides,
  });
}

/** v1 standalone crop response with the renamed rendition. */
export function standaloneCrop(
  overrides: PayloadOptions = {},
): CropDusterPayload {
  return standaloneUpload({
    thumbs: {
      "5e4aeac8f": payloadThumb("5e4aeac8f", {
        id: 1,
        width: 674,
        height: 800,
        crop: { x: 0, y: 0, width: 674, height: 800 },
        url: `/media/${STANDALONE_DIR}/5e4aeac8f.jpg`,
        changed: true,
      }),
    },
    ...overrides,
  });
}
