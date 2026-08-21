/**
 * Return a completed crop to the popup or iframe opener through same-origin
 * function calls.
 *
 * Do not replace this with `postMessage`: a downstream admin script installs
 * a one-shot namespaced `message` handler that would consume the crop
 * message before its own save handshake.
 */

import type { LegacyCropDuster } from "../compat/globalApi";
import type { LegacyCompletePayload } from "../formset/legacyPayload";
import type { DialogRendererData } from "../state/types";

/**
 * The opener, as this side of the boundary uses it: `window.CropDuster` for a
 * change form, or a callback the opener registered under a name of its own.
 */
interface ParentWindow extends Window {
  CropDuster?: LegacyCropDuster;
  [callback: string]: unknown;
}

/**
 * The window that opened this one, or null when there is none.
 *
 * `window.parent` is `window` itself at the top level, which is 4.x's test for
 * "nobody opened us"; a dialog in that state has nowhere to report to.
 */
export function resolveParent(view: Window = window): ParentWindow | null {
  const parent = (view.opener ?? view.parent) as ParentWindow | null;
  if (!parent || parent === view) {
    return null;
  }
  return parent;
}

export interface CompletionTarget {
  /** The opener's own name for the field, echoed from the dialog's GET params. */
  elId: string | null;
  /** CKEditor's channel, which takes precedence when present. */
  callbackFn: string | null;
}

/**
 * Deliver a crop response, and say whether anyone took it.
 *
 * The callback is invoked with its own name as the first argument: CKEditor's
 * dialog registers one function per widget instance and 4.x passed the name
 * where `CropDuster.complete` takes a prefix, so the two channels share a
 * signature.
 */
export function deliverCompletion(
  payload: LegacyCompletePayload,
  target: CompletionTarget,
  view: Window = window,
  rendererData?: DialogRendererData,
): boolean {
  const parent = resolveParent(view);
  if (!parent) {
    return false;
  }
  if (target.callbackFn) {
    const callback = parent[target.callbackFn];
    if (typeof callback === "function") {
      (callback as (name: string, payload: LegacyCompletePayload) => void)(
        target.callbackFn,
        payload,
      );
      return true;
    }
    return false;
  }
  if (parent.CropDuster && target.elId) {
    if (rendererData === undefined) {
      parent.CropDuster.complete(target.elId, payload);
    } else {
      parent.CropDuster.complete(target.elId, payload, rendererData);
    }
    return true;
  }
  return false;
}

/**
 * Close the dialog window.
 *
 * A no-op in CKEditor's iframe, which is not a window a script may close; the
 * plugin's own OK handler hides the dialog there.
 */
export function closeDialogWindow(view: Window = window): void {
  view.close();
}
