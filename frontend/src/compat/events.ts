/**
 * Compatibility events used by the 4.x widget.
 *
 * `cropduster:update` is sent as a native CustomEvent and through each jQuery
 * instance. A document-level jQuery handler therefore sees both calls; only
 * the explicit jQuery event includes the positional `prefix` and `data`
 * arguments.
 */

import { onAll, triggerOnAll } from "../dom/jquery";

export const UPDATE_EVENT = "cropduster:update";
export const SIZES_CHANGE_EVENT = "cropduster:sizeschange";

export interface CropDusterUpdateDetail {
  prefix: string;
  data: unknown;
}

/** Dispatch the completion events for `prefix`. */
export function emitUpdate(prefix: string, data: unknown) {
  document.dispatchEvent(
    new CustomEvent<CropDusterUpdateDetail>(UPDATE_EVENT, {
      detail: { prefix, data },
      bubbles: true,
    }),
  );
  triggerOnAll(document, UPDATE_EVENT, [prefix, data]);
}

/**
 * Report a change to the mutable `sizes` array, which had no event in 4.x.
 */
export function emitSizesChange(prefix: string) {
  document.dispatchEvent(
    new CustomEvent<{ prefix: string }>(SIZES_CHANGE_EVENT, {
      detail: { prefix },
      bubbles: true,
    }),
  );
}

/** nested-admin events that mean "rows were added, renamed or re-inited". */
export const DJNESTING_EVENTS = [
  "djnesting:added",
  "djnesting:attrchange",
  "djnesting:initialized",
] as const;

/**
 * Rescan after native formset additions and django-nested-admin row events.
 * Custom-element connection remains the normal mount path.
 */
export function bindRescanListeners(rescan: () => void): () => void {
  const onNative = () => rescan();
  document.addEventListener("formset:added", onNative);

  const unbinders: (() => void)[] = [
    () => document.removeEventListener("formset:added", onNative),
  ];

  for (const type of DJNESTING_EVENTS) {
    unbinders.push(onAll(document, type, onNative));
  }

  return () => {
    for (const unbind of unbinders) {
      unbind();
    }
  };
}
