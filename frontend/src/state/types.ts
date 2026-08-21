/**
 * Dialog state types. Crop entries refer to source images by id so additional
 * per-crop sources can be added without changing crop geometry.
 */

import type { CropBox, Size } from "../crop/geometry";

export type { CropBox, Size };

export const PRIMARY_SOURCE_ID = "primary";

export type SourceId = string;

/** Renderer URLs passed beside the frozen legacy completion payload. */
export interface RendererImageData {
  url: string | null;
  srcset: string | null;
}

export interface DialogRendererData {
  preview: RendererImageData;
  thumbs: Record<string, RendererImageData>;
}

export type DialogPhase =
  "upload" | "uploading" | "crop" | "saving" | "complete";

/**
 * Original dimensions and the preview dimensions shown by the crop canvas.
 * Crop boxes use source pixels; `crop/scaling.ts` converts to display pixels.
 */
export interface SourceImage {
  id: SourceId;
  /** `cropduster.Image` pk, null until the image row exists. */
  imageId: number | null;
  /** Storage-relative name of the original. */
  name: string;
  /** Renderer URL of the original file, for viewing it at full size. */
  url: string | null;
  width: number;
  height: number;
  displayUrl: string;
  displaySrcset: string | null;
  displayWidth: number;
  displayHeight: number;
}

/** One size's crop, keyed in `DialogState.crops` by raw size name. */
export interface CropEntry {
  sourceId: SourceId;
  /** Null when the size has no crop yet. */
  box: CropBox | null;
  /** Whether the box differs from what the server holds. */
  changed: boolean;
}

export interface ThumbCrop {
  x: number;
  y: number;
  width: number;
  height: number;
}

/** A generated thumbnail in dialog state. */
export interface ThumbState {
  id: number | null;
  name: string;
  /** Null for a crop that has been proposed but never rendered. */
  width: number | null;
  height: number | null;
  /** Renderer URL displayed by the canvas and widget. */
  url: string | null;
  /** Storage file returned to existing completion callbacks. */
  fileUrl: string | null;
  srcset: string | null;
  crop: ThumbCrop | null;
  /** Name of the thumb this one is a rendition of, if any. */
  ref: string | null;
  refId: number | null;
  /** Whether the file is at its tmp path, pending a parent save. */
  tmp: boolean;
  changed: boolean;
  sourceId: SourceId | null;
}

export interface DialogWarning {
  /** Null for a warning the server raised as bare prose. */
  code: string | null;
  message: string;
}

export interface DialogState {
  phase: DialogPhase;
  /** The standalone (CKEditor) dialog, which crops to an editor-chosen size. */
  standalone: boolean;
  sources: Record<SourceId, SourceImage>;
  sizes: Size[];
  /** Index into `sizes` of the size being cropped. */
  index: number;
  /** Keyed by raw size name. */
  crops: Record<string, CropEntry>;
  /** Keyed by raw thumb name. */
  thumbs: Record<string, ThumbState>;
  warnings: DialogWarning[];
  /** Editor-facing message returned by the server. */
  error: string | null;
  /** Stable code used for branching; null without a structured error. */
  errorCode: string | null;
  errorField: string | null;
}
