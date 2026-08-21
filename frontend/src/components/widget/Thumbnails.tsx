/**
 * Render the widget's read-only summary of the crop dialog: the original's
 * name and dimensions, a scaled-down preview of the uncropped image, a card
 * per configured size showing its rendition, and the staged-deletion toggle.
 *
 * The preview keeps the classes and nesting 4.x rendered: one
 * `a.cropduster-image.cropduster-image-preview` around one
 * `img.cropduster-image-thumb`, which downstream styles and tests select on;
 * everything else here is additive, under new `cropduster-` class names.
 */

import { IMAGE, IMAGE_THUMB, PREVIEW_SLUG } from "../../constants/classNames";
import type { Size } from "../../crop/geometry";
import type { WidgetThumb } from "../../formset/FormsetBridge";
import {
  displayFilename,
  imageDetail,
  isStoredImagePath,
} from "../../lib/filename";
import { useWidget } from "./context";

const DELETE_LABEL = "Delete image";
const UNDELETE_LABEL = "Undo delete";
const DELETED_NOTE = "Removed when the form is saved.";

/** The rail's rendition box; mirrors `.cropduster-crop-thumb` in card.css. */
const CROP_MAX_WIDTH = 120;
const CROP_MAX_HEIGHT = 64;
/** The preview's height cap; mirrors `.cropduster-image-thumb`. */
const PREVIEW_MAX_HEIGHT = 180;

/**
 * The box an image of known dimensions occupies under a maximum size,
 * reserved as an explicit style so an image whose file has not arrived yet
 * holds its place instead of collapsing to a bordered dot.
 */
function reservedBox(
  width: number | null,
  height: number | null,
  maxWidth: number,
  maxHeight: number,
): { width: number; height: number } | null {
  if (!width || !height || width < 0 || height < 0) {
    return null;
  }
  const fit = Math.min(1, maxWidth / width, maxHeight / height);
  return { width: Math.round(width * fit), height: Math.round(height * fit) };
}

interface CropCard {
  key: string;
  label: string;
  thumb: WidgetThumb | null;
}

/**
 * The URL a rendition is displayed from: the configured renderer's when the
 * markup includes one, otherwise the stored file, which is all a 4.x-shaped
 * write provides.
 */
function displayUrl(thumb: WidgetThumb | null): string | null {
  return thumb ? (thumb.rendererUrl ?? thumb.url) : null;
}

/**
 * One card per configured size, matched to its rendition by the raw size
 * name; a size's `auto` renditions are not sizes and so are not shown. For
 * markup without a size list, fall back to every rendition with a URL.
 */
function cropCards(sizes: Size[], thumbs: WidgetThumb[]): CropCard[] {
  if (sizes.length) {
    return sizes.map((size, index) => {
      const name = typeof size.name === "string" ? size.name : "";
      return {
        key: name || String(index),
        label: size.label || name,
        thumb: thumbs.find((thumb) => thumb.name === name) ?? null,
      };
    });
  }
  return thumbs
    .filter((thumb) => displayUrl(thumb))
    .map((thumb) => ({ key: thumb.name, label: thumb.name, thumb }));
}

export function Thumbnails() {
  const { state, bridge } = useWidget();

  if (!isStoredImagePath(state.origImage)) {
    return null;
  }

  const { url, rendererUrl, srcset, width, height } = state.preview;
  const previewSrc = rendererUrl || url;
  const previewW = Number(width) || null;
  const previewH = Number(height) || null;
  const previewBox = reservedBox(
    previewW,
    previewH,
    Number.POSITIVE_INFINITY,
    PREVIEW_MAX_HEIGHT,
  );
  const filename = displayFilename(state.origImage);
  const detail = imageDetail(state.origWidth, state.origHeight, filename);
  const cards = cropCards(bridge.readSizes(), state.thumbs);

  return (
    <div
      className={
        state.deleted
          ? "cropduster-card cropduster-card-deleted"
          : "cropduster-card"
      }
      part={state.deleted ? "card card-deleted" : "card"}
    >
      <div className="cropduster-card-header" part="header">
        <div className="cropduster-card-meta" part="meta">
          <div
            className="cropduster-card-filename"
            part="filename"
            title={filename}
          >
            {filename}
          </div>
          {detail ? (
            <div className="cropduster-card-detail" part="detail">
              {detail}
            </div>
          ) : null}
        </div>
        {state.canDelete ? (
          <div className="cropduster-card-actions" part="actions">
            {state.deleted ? (
              <span className="cropduster-card-note" part="note">
                {DELETED_NOTE}
              </span>
            ) : null}
            <button
              type="button"
              className="cropduster-delete-button"
              part="delete-button"
              onClick={() => bridge.setDeleted(!state.deleted)}
            >
              {state.deleted ? UNDELETE_LABEL : DELETE_LABEL}
            </button>
          </div>
        ) : null}
      </div>
      <a
        target="_blank"
        className={`${IMAGE} ${IMAGE}-${PREVIEW_SLUG}`}
        part="preview"
        href={url}
      >
        <img
          className={`${IMAGE_THUMB} ${IMAGE_THUMB}-${PREVIEW_SLUG}`}
          part="preview-image"
          src={previewSrc}
          srcSet={srcset || undefined}
          width={width}
          height={height}
          style={
            previewBox
              ? {
                  // The stylesheet also caps the preview at the card's width;
                  // the aspect ratio keeps the reserved height in step when
                  // that cap is the one that binds.
                  width: `min(100%, ${previewBox.width}px)`,
                  aspectRatio: `${previewW} / ${previewH}`,
                }
              : undefined
          }
        />
      </a>
      {cards.length ? (
        <div className="cropduster-card-rail" part="rail">
          {cards.map((card) => {
            const cropUrl = displayUrl(card.thumb);
            const cropBox = card.thumb
              ? reservedBox(
                  card.thumb.width,
                  card.thumb.height,
                  CROP_MAX_WIDTH,
                  CROP_MAX_HEIGHT,
                )
              : null;
            return (
              <div className="cropduster-crop" part="crop" key={card.key}>
                <span
                  className={
                    cropUrl
                      ? "cropduster-crop-frame"
                      : "cropduster-crop-frame cropduster-crop-pending"
                  }
                  part={cropUrl ? "crop-frame" : "crop-frame crop-pending"}
                >
                  {cropUrl && card.thumb ? (
                    <img
                      className="cropduster-crop-thumb"
                      part="crop-image"
                      src={cropUrl}
                      srcSet={card.thumb.rendererSrcset ?? undefined}
                      width={card.thumb.width ?? undefined}
                      height={card.thumb.height ?? undefined}
                      style={cropBox ?? undefined}
                      alt=""
                    />
                  ) : null}
                </span>
                <span
                  className="cropduster-crop-label"
                  part="crop-label"
                  title={card.label}
                >
                  {card.label}
                </span>
              </div>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
