/** Operations supplied by the page or modal containing `DialogApp`. */

import { createContext, useContext } from "react";

import type { DialogModel } from "../../state/dialogReducer";
import type { LegacyCompletePayload } from "../../formset/legacyPayload";
import type { DialogRendererData } from "../../state/types";

/**
 * Methods called by CKEditor's outer dialog because the crop button is inside
 * a shadow root.
 *
 * `state` is a getter so the caller reads it at click time.
 */
export interface DialogWindowApi {
  /** Whether every crop is populated and Save can run. */
  canCommit(): boolean;
  /** Save the complete crop set, as clicking `#crop-button` would. */
  commit(): void;
  readonly state: DialogModel;
}

declare global {
  interface Window {
    /**
     * The dialog methods published on the popup, CKEditor iframe, or page
     * containing a modal. Removed when the dialog closes.
     */
    CropDusterDialog?: DialogWindowApi;
  }
}

export interface ShellContextValue {
  /** The rendering root, for anything that has to measure or portal. */
  container: HTMLElement;
  /**
   * A finished crop, returned to the dialog's opener.
   *
   * `rendererData` contains preview and crop URLs that the frozen legacy
   * payload has no fields for.
   */
  onCommit(
    payload: LegacyCompletePayload,
    rendererData?: DialogRendererData,
  ): void;
  /** The editor closed the dialog without finishing. */
  onCancel(): void;
  /** Publish (or withdraw, with null) the imperative handle. */
  publish?(api: DialogWindowApi | null): void;
}

export const ShellContext = createContext<ShellContextValue | null>(null);

export function useShell(): ShellContextValue {
  const shell = useContext(ShellContext);
  if (!shell) {
    throw new Error("cropduster: dialog rendered outside a shell");
  }
  return shell;
}
