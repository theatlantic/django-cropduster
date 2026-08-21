/** Keep a real `#id_image` file input so Selenium can send it a local path. */

import { useCallback, useEffect, useRef, useState } from "react";

import { BUTTON, DISABLED } from "../../constants/classNames";
import {
  CANCEL,
  MIN_SIZE_PREFIX,
  UPLOAD,
  UPLOAD_IMAGE,
  UPLOADING,
  replaceWarning,
} from "../../constants/dialogLabels";
import { dialogStage, overallMinSize } from "../../state/dialogReducer";
import { useDialog } from "../../state/DialogContext";

function classes(...names: (string | false)[]): string {
  return names.filter(Boolean).join(" ");
}

export function UploadStep() {
  const { state, controller } = useDialog();
  const inputRef = useRef<HTMLInputElement>(null);
  const [fileName, setFileName] = useState("");
  const stage = dialogStage(state);
  const uploading = state.phase === "uploading";
  const uploadDisabled = !state.fileSelected || uploading;

  const onChange = useCallback(() => {
    const file = inputRef.current?.files?.[0] ?? null;
    setFileName(file?.name ?? "");
    controller.selectFile(file);
    if (file && !state.standalone && stage === "upload") {
      controller.upload();
    }
  }, [controller, stage, state.standalone]);

  // Clear a consumed selection. Automatic-upload errors clear `fileSelected`,
  // so choosing the same file dispatches another change event and retries.
  useEffect(() => {
    if (!state.fileSelected && inputRef.current?.value) {
      inputRef.current.value = "";
      setFileName("");
    }
  }, [state.fileSelected]);

  useEffect(() => {
    if (!state.standalone && stage === "upload" && state.error) {
      inputRef.current?.focus();
    }
  }, [stage, state.error, state.standalone]);

  const [minW, minH] = overallMinSize(state.sizes);
  const minSize = `${MIN_SIZE_PREFIX}${minW} x ${minH}`;
  const describedBy =
    [
      state.replacing ? "replace-image-help" : null,
      state.sizes.length ? "upload-min-size-help" : null,
    ]
      .filter(Boolean)
      .join(" ") || undefined;

  if (state.standalone) {
    return (
      <div className="row form-row image" part="upload-row">
        <input
          id="id_image"
          type="file"
          part="file-input"
          ref={inputRef}
          disabled={uploading}
          onChange={onChange}
        />
      </div>
    );
  }

  return (
    <div
      className="row form-row image upload-stage"
      part="upload-row upload-stage"
    >
      {state.replacing ? (
        <p id="replace-image-help" className="upload-stage-copy">
          {replaceWarning(state.sizes.length)}
        </p>
      ) : null}
      <label
        className="upload-file-control"
        part="file-control"
        aria-busy={uploading}
      >
        <svg
          className="upload-file-icon"
          viewBox="0 0 24 24"
          aria-hidden="true"
        >
          <path d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5M5 14v4.5A1.5 1.5 0 0 0 6.5 20h11a1.5 1.5 0 0 0 1.5-1.5V14" />
        </svg>
        <span className="upload-file-title">
          {uploading ? UPLOADING : fileName || UPLOAD_IMAGE}
        </span>
        <span className="upload-file-detail">
          {state.sizes.length ? minSize : "Select an image file"}
        </span>
        <input
          id="id_image"
          className="upload-file-input"
          type="file"
          part="file-input"
          ref={inputRef}
          disabled={uploading}
          aria-describedby={describedBy}
          onChange={onChange}
        />
      </label>
      {state.sizes.length ? (
        <div
          id="upload-min-size-help"
          part="min-size-help"
          className="visually-hidden"
        >
          {minSize}
        </div>
      ) : null}
      <ul
        className="submit-row upload-stage-actions"
        id="upload-footer"
        part="actions upload-actions"
        hidden={stage !== "upload" || !state.replacing}
      >
        {state.replacing ? (
          <li className="submit-button-container" part="actions-item">
            <input
              id="cancel-replace-button"
              type="button"
              part="button cancel-replace-button"
              className={classes(
                BUTTON,
                "cropduster-button-secondary",
                uploading && DISABLED,
              )}
              disabled={uploading}
              value={CANCEL}
              onClick={() => controller.cancelReplace()}
            />
          </li>
        ) : null}
      </ul>
      <div className="legacy-upload-controls" hidden>
        <input
          id="upload-button"
          type="button"
          part="button upload-button"
          className={classes(BUTTON, uploadDisabled && DISABLED)}
          disabled={uploadDisabled}
          value={uploading ? UPLOADING : UPLOAD}
          onClick={() => controller.upload()}
        />
      </div>
    </div>
  );
}
