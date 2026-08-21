/** Shared dialog component tree for the page and modal containers. */

import { useEffect, useRef } from "react";

import {
  CROP_HEADER_PREFIX,
  REPLACE_IMAGE_HEADER,
} from "../../constants/dialogLabels";
import { DialogProvider, useDialog } from "../../state/DialogContext";
import type { DialogConfig } from "../../state/dialogConfig";
import {
  currentSize,
  dialogStage,
  primarySource,
} from "../../state/dialogReducer";
import { CropNav } from "./CropNav";
import { CropStep } from "./CropStep";
import { ErrorBanner } from "./ErrorBanner";
import { SizeForm } from "./SizeForm";
import { SourceChip } from "./SourceChip";
import { UploadStep } from "./UploadStep";

function DialogBody() {
  const { state } = useDialog();
  const rootRef = useRef<HTMLDivElement>(null);
  const hasImage = Boolean(primarySource(state).name);
  const sizeLabel = currentSize(state)?.label;
  const stage = dialogStage(state);
  const previousStage = useRef(stage);

  // Page stylesheets can restyle the dialog through the `part` attributes
  // below (`cropduster-dialog::part(...)`), but an attribute selector cannot
  // follow `::part()`, so state-dependent styling needs the phase on the
  // shadow host itself.
  useEffect(() => {
    const root = rootRef.current?.getRootNode();
    const host = root instanceof ShadowRoot ? root.host : null;
    if (!host) {
      return;
    }
    host.setAttribute("data-phase", state.phase);
    host.setAttribute("data-stage", stage);
    if (hasImage) {
      host.setAttribute("data-image", "");
    } else {
      host.removeAttribute("data-image");
    }
    if (state.replacing) {
      host.setAttribute("data-replacing", "");
    } else {
      host.removeAttribute("data-replacing");
    }
    if (state.fileSelected) {
      host.setAttribute("data-file", "");
    } else {
      host.removeAttribute("data-file");
    }
  }, [hasImage, stage, state.phase, state.replacing, state.fileSelected]);

  // File selection replaces the focused upload control without another click.
  // Focus the new step so the transition is exposed to keyboard users.
  useEffect(() => {
    if (
      !state.standalone &&
      previousStage.current === "upload" &&
      stage === "crop"
    ) {
      rootRef.current?.querySelector<HTMLElement>("#step-header")?.focus();
    }
    previousStage.current = stage;
  }, [stage, state.standalone]);

  const heading =
    stage === "upload"
      ? REPLACE_IMAGE_HEADER
      : `${CROP_HEADER_PREFIX}${sizeLabel ? `: ${sizeLabel}` : ""}`;
  const showHeader = stage === "crop" || state.replacing;

  return (
    <div
      ref={rootRef}
      className="cropduster-dialog"
      part="dialog"
      data-phase={state.phase}
      data-stage={state.standalone ? undefined : stage}
      data-standalone={state.standalone ? "" : undefined}
      data-image={hasImage ? "" : undefined}
      data-replacing={state.replacing ? "" : undefined}
      data-file={state.fileSelected ? "" : undefined}
    >
      {!state.standalone && showHeader ? (
        <div className="dialog-header" part="header">
          <h1 id="step-header" part="step-header" tabIndex={-1}>
            {heading}
          </h1>
          {stage === "crop" && hasImage ? <SourceChip /> : null}
        </div>
      ) : null}
      <fieldset
        className="module aligned"
        part="fields"
        hidden={!state.standalone && stage !== "upload"}
      >
        <UploadStep />
        {state.standalone ? <SizeForm /> : null}
      </fieldset>
      <ErrorBanner />
      <CropStep />
      <CropNav />
    </div>
  );
}

export interface DialogAppProps {
  config: DialogConfig;
}

export function DialogApp({ config }: DialogAppProps) {
  return (
    <DialogProvider config={config}>
      <DialogBody />
    </DialogProvider>
  );
}
