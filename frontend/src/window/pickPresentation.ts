/**
 * Select a modal or separate-window crop dialog.
 *
 * Explicit settings take precedence. `auto` uses the current viewport size;
 * the 900x600 cutoff sends a downstream 830x550 iframe embed through the
 * existing window flow and avoids its one-shot namespaced `message`
 * handler.
 */

import type { DialogMode } from "../dom/config";

/** Minimum viewport size used by `auto` for the modal. */
export const MIN_MODAL_WIDTH = 900;
export const MIN_MODAL_HEIGHT = 600;

export type DialogPresentation = "modal" | "window";

export interface PresentationConfig {
  dialogMode: DialogMode;
}

/** Return true when the viewport meets the modal's minimum dimensions. */
export function fitsModal(view: Window = window): boolean {
  return (
    view.innerWidth >= MIN_MODAL_WIDTH && view.innerHeight >= MIN_MODAL_HEIGHT
  );
}

export function pickPresentation(
  config: PresentationConfig,
  view: Window = window,
): DialogPresentation {
  if (config.dialogMode === "modal" || config.dialogMode === "window") {
    return config.dialogMode;
  }
  return fitsModal(view) ? "modal" : "window";
}
