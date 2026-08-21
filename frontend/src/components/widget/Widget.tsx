/**
 * Render the upload button and preview through portals while leaving named
 * form inputs under Django's control.
 */

import { useEffect, useMemo, useSyncExternalStore } from "react";
import { createPortal } from "react-dom";

import { GRP_PREDELETE, NO_IMAGE, PREDELETE } from "../../constants/classNames";
import type { WidgetInstance } from "../../dom/WidgetInstance";
import { isStoredImagePath } from "../../lib/filename";
import { Thumbnails } from "./Thumbnails";
import { UploadButton } from "./UploadButton";
import { WidgetContext } from "./context";
import type { WidgetContextValue } from "./context";

export interface WidgetProps {
  instance: WidgetInstance;
}

export function Widget({ instance }: WidgetProps) {
  const state = useSyncExternalStore(instance.subscribe, instance.getState);
  const { root, config, bridge, slots } = instance;

  // grappelli and nested-admin both style a row pending deletion by class;
  // the classes are set on the wrapper so the caption and attribution
  // fields dim too.
  useEffect(() => {
    root.classList.toggle(PREDELETE, state.deleted);
    root.classList.toggle(GRP_PREDELETE, state.deleted);
  }, [root, state.deleted]);

  // The caption and attribution inputs describe an image; without one they
  // are hidden along with the rest of the summary.
  useEffect(() => {
    root.classList.toggle(NO_IMAGE, !isStoredImagePath(state.origImage));
  }, [root, state.origImage]);

  const value = useMemo<WidgetContextValue>(
    () => ({ root, config, bridge, slots, state }),
    [root, config, bridge, slots, state],
  );

  return (
    <WidgetContext.Provider value={value}>
      {slots.button ? createPortal(<UploadButton />, slots.button) : null}
      {slots.cards ? createPortal(<Thumbnails />, slots.cards) : null}
    </WidgetContext.Provider>
  );
}
