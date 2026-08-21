/**
 * Render crop progression and source actions.
 *
 * The modal uses a visual preview rail as its size navigator. Standalone
 * CKEditor keeps the compact 4.x footer because its host supplies the final
 * commit action.
 */

import type { CSSProperties, KeyboardEvent } from "react";

import { BUTTON, DISABLED } from "../../constants/classNames";
import {
  ALL_CROPS_SET,
  CROP_PREVIEWS_LABEL,
  LOADING_CROPS,
  NEXT_SIZE_LABEL,
  NO_CHANGES_YET,
  PREV_SIZE_LABEL,
  REUPLOAD,
  SAVE,
  SAVING,
  UPLOAD,
  UPLOADING,
  cropsProgress,
  nextCropLabel,
} from "../../constants/dialogLabels";
import type { Size } from "../../crop/geometry";
import { thumbForSize } from "../../formset/legacyPayload";
import {
  cropKey,
  currentSize,
  dialogStage,
  nextPendingIndex,
  populatedCropCount,
  primarySource,
} from "../../state/dialogReducer";
import type { DialogModel } from "../../state/dialogReducer";
import { useDialog } from "../../state/DialogContext";
import { PRIMARY_SOURCE_ID } from "../../state/types";

function classes(...names: (string | false)[]): string {
  return names.filter(Boolean).join(" ");
}

/** A spec axis, with a minimum of exactly 1 meaning "no minimum". */
function specAxis(dim: unknown, min: unknown): number {
  return Number(dim) || (Number(min) > 1 ? Number(min) : 0);
}

function cropPreviewSource(state: DialogModel, size: Size) {
  const entry = state.crops[cropKey(size)];
  return (
    state.sources[entry?.sourceId ?? PRIMARY_SOURCE_ID] ?? primarySource(state)
  );
}

function cropPreviewStyle(state: DialogModel, size: Size): CSSProperties {
  const entry = state.crops[cropKey(size)];
  const box = entry?.box;
  // A crop takes its own shape. A pending size is shaped by its spec only
  // when the spec fixes both axes; a free axis would degenerate into a
  // sliver, so those get the plain full-frame rectangle instead.
  const specW = specAxis(size.w, size.min_w);
  const specH = specAxis(size.h, size.min_h);
  const [ratioW, ratioH] = box
    ? [box.w, box.h]
    : specW && specH
      ? [specW, specH]
      : [58, 48];
  const ratio = ratioW / ratioH;
  const frameRatio = 58 / 48;
  const width = ratio >= frameRatio ? 58 : 48 * ratio;
  const height = ratio >= frameRatio ? 58 / ratio : 48;
  const style: CSSProperties = {
    width,
    height,
    aspectRatio: `${ratioW} / ${ratioH}`,
  };
  return style;
}

function cropPreviewSourceStyle(
  state: DialogModel,
  size: Size,
): CSSProperties | undefined {
  const box = state.crops[cropKey(size)]?.box;
  const source = cropPreviewSource(state, size);
  if (!box || !source.displayUrl || !source.width || !source.height) {
    return undefined;
  }
  return {
    position: "absolute",
    width: `${(source.width / box.w) * 100}%`,
    height: `${(source.height / box.h) * 100}%`,
    maxWidth: "none",
    left: `${(-box.x / box.w) * 100}%`,
    top: `${(-box.y / box.h) * 100}%`,
  };
}

function previewDescription(state: DialogModel, size: Size): string {
  const entry = state.crops[cropKey(size)];
  const thumb = thumbForSize(state.thumbs, size, {
    standalone: state.standalone,
  });
  // Saved boxes are still in transit, so an empty card is unknown, not empty.
  if (state.hydrating && !entry?.box) {
    return "Crop loading";
  }
  const saved = Boolean(thumb?.url || thumb?.id);
  const dirty = Boolean(saved && entry?.changed);
  if (entry?.sourceId && entry.sourceId !== PRIMARY_SOURCE_ID) {
    return dirty
      ? "Override crop with unsaved changes"
      : "Override crop available";
  }
  if (dirty) {
    return "Saved crop with unsaved changes";
  }
  if (saved) {
    return "Saved crop available";
  }
  if (entry?.box) {
    return "Crop available";
  }
  return "No crop yet";
}

function CropPreview({
  state,
  size,
  index,
  current,
  disabled,
  onSelect,
  onKeyDown,
}: {
  state: DialogModel;
  size: Size;
  index: number;
  current: boolean;
  disabled: boolean;
  onSelect(): void;
  onKeyDown(event: KeyboardEvent<HTMLButtonElement>): void;
}) {
  const thumb = thumbForSize(state.thumbs, size, {
    standalone: state.standalone,
  });
  const entry = state.crops[cropKey(size)];
  const source = cropPreviewSource(state, size);
  const sourceStyle = cropPreviewSourceStyle(state, size);
  const hasLiveBox = Boolean(state.crops[cropKey(size)]?.box);
  const hasPreview = hasLiveBox || Boolean(thumb?.url);
  const dirty = Boolean(entry?.changed && (thumb?.url || thumb?.id));
  const description = previewDescription(state, size);
  const label = size.label || String(size.name || `Crop ${index + 1}`);

  return (
    <button
      id={`crop-preview-${index}`}
      type="button"
      className={classes(
        "crop-preview",
        current && "current",
        dirty && "dirty",
        disabled && DISABLED,
      )}
      part={classes(
        "crop-preview",
        current && "crop-preview-current",
        dirty && "crop-preview-dirty",
      )}
      title={label}
      aria-current={current ? "step" : undefined}
      aria-label={`${label}, ${description}, crop ${index + 1} of ${state.sizes.length}`}
      tabIndex={current && !disabled ? 0 : -1}
      disabled={disabled}
      data-has-preview={hasPreview ? "" : undefined}
      data-dirty={dirty ? "" : undefined}
      onClick={onSelect}
      onKeyDown={onKeyDown}
    >
      <span
        className={classes("crop-preview-image", !hasPreview && "empty")}
        part={classes(
          "crop-preview-image",
          !hasPreview && "crop-preview-empty",
        )}
        aria-hidden="true"
        style={cropPreviewStyle(state, size)}
      >
        {hasLiveBox && source.displayUrl && sourceStyle ? (
          <img
            className="crop-preview-source"
            src={source.displayUrl}
            srcSet={source.displaySrcset ?? undefined}
            alt=""
            draggable={false}
            style={sourceStyle}
          />
        ) : thumb?.url ? (
          <img
            className="crop-preview-rendition"
            src={thumb.url}
            srcSet={thumb.srcset ?? undefined}
            alt=""
            draggable={false}
          />
        ) : null}
      </span>
    </button>
  );
}

export function CropNav() {
  const { state, controller } = useDialog();

  const hasImage = Boolean(primarySource(state).name);
  const stage = dialogStage(state);
  const cropStage = stage === "crop";
  const uploading = state.phase === "uploading";
  const saving = state.phase === "saving";
  const uploadDisabled = !state.fileSelected || uploading;
  const saveDisabled = !controller.canCommit();
  const showSave = !saveDisabled || saving;

  const count = state.sizes.length;
  const navigationDisabled = state.phase !== "crop" || state.hydrating;
  const navHidden = count <= 1;
  const leftDisabled = navigationDisabled || state.index <= 0;
  const rightDisabled = navigationDisabled || state.index + 1 >= count;

  if (state.standalone) {
    return (
      <footer className="footer submit-row" part="footer">
        <div id="crop-nav" part="nav" hidden={navHidden}>
          <button
            type="button"
            id="nav-left"
            part="nav-button nav-left"
            className={classes(BUTTON, leftDisabled && DISABLED)}
            disabled={leftDisabled}
            aria-label={PREV_SIZE_LABEL}
            onClick={() => controller.navigate(-1)}
          >
            <span part="nav-arrow nav-arrow-left" />
          </button>
          <button
            type="button"
            id="nav-right"
            part="nav-button nav-right"
            className={classes(BUTTON, rightDisabled && DISABLED)}
            disabled={rightDisabled}
            aria-label={NEXT_SIZE_LABEL}
            onClick={() => controller.navigate(1)}
          >
            <span part="nav-arrow nav-arrow-right" />
          </button>
        </div>
        <div id="current-thumb-info" part="counter" hidden={navHidden}>
          <div id="current-thumb-index" part="counter-index">
            {state.index + 1}
          </div>
          <div id="thumb-total-count" part="counter-total">
            {count}
          </div>
          <div id="current-thumb-label" part="counter-label">
            {currentSize(state)?.label ?? ""}
          </div>
        </div>
        <ul
          className="submit-row"
          id="upload-footer"
          part="actions upload-actions"
          hidden={hasImage}
        >
          <li className="submit-button-container" part="actions-item">
            <input
              id="upload-button"
              type="button"
              part="button upload-button"
              className={classes(BUTTON, uploadDisabled && DISABLED)}
              disabled={uploadDisabled}
              value={uploading ? UPLOADING : UPLOAD}
              onClick={() => controller.upload()}
            />
          </li>
        </ul>
        <ul
          className="submit-row"
          id="crop-footer"
          part="actions crop-actions"
          hidden={!hasImage}
        >
          <li className="submit-button-container" part="actions-item">
            <input
              id="crop-button"
              type="button"
              part="button crop-button"
              className={classes(BUTTON, saveDisabled && DISABLED)}
              disabled={saveDisabled}
              value={saving ? SAVING : SAVE}
              onClick={() => controller.save()}
            />
          </li>
          <li className="submit-button-container" part="actions-item">
            <input
              id="reupload-button"
              type="button"
              part="button reupload-button"
              className={classes(BUTTON, uploadDisabled && DISABLED)}
              disabled={uploadDisabled}
              value={uploading ? UPLOADING : REUPLOAD}
              onClick={() => controller.upload()}
            />
          </li>
        </ul>
      </footer>
    );
  }

  const onPreviewKeyDown = (
    event: KeyboardEvent<HTMLButtonElement>,
    index: number,
  ) => {
    let target = index;
    if (event.key === "ArrowLeft") {
      target = Math.max(0, index - 1);
    } else if (event.key === "ArrowRight") {
      target = Math.min(count - 1, index + 1);
    } else if (event.key === "Home") {
      target = 0;
    } else if (event.key === "End") {
      target = count - 1;
    } else {
      return;
    }
    event.preventDefault();
    controller.navigateTo(target);
    event.currentTarget.parentElement
      ?.querySelector<HTMLElement>(`#crop-preview-${target}`)
      ?.focus();
  };

  const populated = populatedCropCount(state);
  const nextPending = nextPendingIndex(state);
  const nextSize = nextPending === -1 ? null : state.sizes[nextPending];
  // A hydrating dialog is waiting on the saved boxes; "0 of N crops set"
  // would misreport that wait as an empty result.
  const progress =
    count === 0
      ? ""
      : state.hydrating
        ? LOADING_CROPS
        : populated < count
          ? cropsProgress(populated, count)
          : state.dirty
            ? ALL_CROPS_SET
            : NO_CHANGES_YET;

  return (
    <footer
      className="footer crop-tray"
      part="footer crop-tray"
      aria-label={CROP_PREVIEWS_LABEL}
      hidden={!cropStage}
    >
      <div
        id="current-thumb-info"
        part="counter"
        aria-live="polite"
        hidden={!cropStage}
      >
        <div id="current-thumb-index" part="counter-index">
          {state.index + 1}
        </div>
        <div id="thumb-total-count" part="counter-total">
          {count}
        </div>
        <div id="current-thumb-label" part="counter-label">
          {currentSize(state)?.label ?? ""}
        </div>
      </div>
      <button
        type="button"
        id="nav-left"
        part="nav-button nav-left"
        className={classes(BUTTON, "crop-tray-nav", leftDisabled && DISABLED)}
        disabled={leftDisabled}
        hidden={navHidden}
        aria-label={PREV_SIZE_LABEL}
        onClick={() => controller.navigate(-1)}
      >
        <span part="nav-arrow nav-arrow-left" />
      </button>
      <nav
        id="crop-nav"
        className="crop-preview-list"
        part="nav"
        aria-label={CROP_PREVIEWS_LABEL}
        hidden={!cropStage}
      >
        {state.sizes.map((size, index) => (
          <CropPreview
            key={`${String(size.name)}-${index}`}
            state={state}
            size={size}
            index={index}
            current={index === state.index}
            disabled={navigationDisabled}
            onSelect={() => controller.navigateTo(index)}
            onKeyDown={(event) => onPreviewKeyDown(event, index)}
          />
        ))}
      </nav>
      <button
        type="button"
        id="nav-right"
        part="nav-button nav-right"
        className={classes(BUTTON, "crop-tray-nav", rightDisabled && DISABLED)}
        disabled={rightDisabled}
        hidden={navHidden}
        aria-label={NEXT_SIZE_LABEL}
        onClick={() => controller.navigate(1)}
      >
        <span part="nav-arrow nav-arrow-right" />
      </button>
      <ul
        className="submit-row crop-tray-actions"
        id="crop-footer"
        part="actions crop-actions"
        hidden={!cropStage}
      >
        {nextSize && !state.hydrating ? (
          <li className="submit-button-container" part="actions-item">
            <input
              id="next-crop-button"
              type="button"
              part="button next-button"
              className={classes(BUTTON, navigationDisabled && DISABLED)}
              disabled={navigationDisabled}
              value={nextCropLabel(
                nextSize.label || String(nextSize.name ?? ""),
              )}
              onClick={() => controller.navigateTo(nextPending)}
            />
          </li>
        ) : null}
        {showSave ? (
          <li className="submit-button-container" part="actions-item">
            <input
              id="crop-button"
              type="button"
              part="button crop-button"
              className={classes(BUTTON, saveDisabled && DISABLED)}
              disabled={saveDisabled}
              value={saving ? SAVING : SAVE}
              onClick={() => controller.save()}
            />
          </li>
        ) : null}
        <li className="crop-progress-item" part="actions-item">
          <span id="crop-progress" part="progress" aria-live="polite">
            {progress}
          </span>
        </li>
      </ul>
      <div className="legacy-reupload-controls" hidden>
        <input
          id="reupload-button"
          type="button"
          part="button reupload-button"
          className={classes(BUTTON, uploadDisabled && DISABLED)}
          disabled={uploadDisabled}
          value={uploading ? UPLOADING : REUPLOAD}
          onClick={() => controller.upload()}
        />
      </div>
    </footer>
  );
}
