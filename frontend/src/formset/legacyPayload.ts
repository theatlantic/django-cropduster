import type { Size } from "../crop/geometry";

export interface LegacyThumb {
  id: number | null;
  name: string;
  width: number | null;
  height: number | null;
  url?: string;
  [key: string]: unknown;
}

export interface LegacyCropData {
  image_id: number | null;
  orig_image: string | null;
  orig_w: number | null;
  orig_h: number | null;
  thumbs: Record<string, LegacyThumb>;
  sizes?: string | Size[] | null;
  standalone?: boolean;
  [key: string]: unknown;
}

export interface LegacyThumbForm {
  id: number | null;
  name: string;
  width?: number | null;
  height?: number | null;
  crop_x?: number | null;
  crop_y?: number | null;
  crop_w?: number | null;
  crop_h?: number | null;
  changed?: boolean;
  url?: string;
  thumbs?: Record<string, LegacyThumb>;
  [key: string]: unknown;
}

export interface LegacyCompletePayload {
  crop: LegacyCropData;
  thumbs: LegacyThumbForm[];
  initial: boolean;
  preview_url: string;
  preview_w: number;
  preview_h: number;
  [key: string]: unknown;
}

export interface LegacyUploadResponse {
  crop: LegacyCropData;
  url: string;
  orig_image: string;
  orig_w: number;
  orig_h: number;
  width: number;
  height: number;
  [key: string]: unknown;
}
