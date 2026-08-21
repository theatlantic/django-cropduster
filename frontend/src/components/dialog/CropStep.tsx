/** Keep the 4.x crop container and image ids mounted for Selenium. */

import { CropCanvas } from "./CropCanvas";
import { dialogStage, primarySource } from "../../state/dialogReducer";
import { useDialog } from "../../state/DialogContext";

export function CropStep() {
  const { state } = useDialog();
  const hasImage = Boolean(primarySource(state).name);
  // The upload stage hides the canvas even when an image exists, which is
  // the case while a replacement is being chosen.
  const hidden = state.standalone
    ? !hasImage
    : dialogStage(state) !== "crop" || !hasImage;

  return (
    <div id="image-container" part="image-frame" hidden={hidden}>
      <CropCanvas />
    </div>
  );
}
