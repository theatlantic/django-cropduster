/** Dialog labels, including the stable action values read by Selenium. */

export const REPLACE_IMAGE_HEADER = "Replace the image";
export const CROP_HEADER_PREFIX = "Set crop";
export const UPLOAD_IMAGE = "Upload an image";
export const UPLOAD = "Upload";
export const UPLOADING = "Uploading...";
export const REUPLOAD = "Re-Upload";
export const CANCEL = "Cancel";
export const SAVE = "Save";
export const SAVING = "Saving...";
export const MIN_SIZE_PREFIX = "Min. size: ";

/** The stage copy shown in place of the help text while replacing. */
export function replaceWarning(sizeCount: number): string {
  return sizeCount === 1
    ? "The crop will be redone after the new image uploads."
    : `Crops for all ${sizeCount} sizes will be redone after the new image uploads.`;
}

/** The source chip and its menu. */
export const IMAGE_CHIP_LABEL = "Image:";
export const SOURCE_MENU_LABEL = "Image source";
export const REPLACE_IMAGE = "Replace the image…";
export const VIEW_FULL_SIZE = "View full size";

/** The replace entry's scope line. */
export function replaceResets(sizeCount: number): string {
  return sizeCount === 1 ? "Resets the crop." : "Resets all crops.";
}

/** The crop checklist's progress text and its Next action. */
export const ALL_CROPS_SET = "All crops set";
export const NO_CHANGES_YET = "No changes yet";
export const LOADING_CROPS = "Loading crops...";

export function cropsProgress(populated: number, total: number): string {
  return `${populated} of ${total} crop${total === 1 ? "" : "s"} set`;
}

export function nextCropLabel(sizeLabel: string): string {
  return `Next: ${sizeLabel} →`;
}
export const CROP_PREVIEWS_LABEL = "Crop previews";
export const WIDTH = "Width";
export const HEIGHT = "Height";

/** The modal's accessible name, and its close button's. */
export const DIALOG_LABEL = "Crop image";
export const CLOSE_LABEL = "Close";

/** Accessible labels for the icon-only navigation buttons. */
export const PREV_SIZE_LABEL = "Previous size";
export const NEXT_SIZE_LABEL = "Next size";
