/**
 * The 4.x `window.CropDuster` API implemented on top of the React widget.
 *
 * Downstream code depends on its write order, option attributes, popup URL and
 * window name, and mutation of the shared sizes array. Install it before
 * DOMContentLoaded so admin scripts can call it from ready handlers.
 */

import { SELECTORS } from "../constants/classNames";
import { openModalDialog } from "../components/dialog/shells/ModalShell";
import { FormsetBridge } from "../formset/FormsetBridge";
import type {
  LegacyCompletePayload,
  LegacyThumb,
} from "../formset/legacyPayload";
import { readData, readSizes, writeData } from "../dom/jquery";
import { registry, rootForPrefix } from "../dom/registry";
import type { WidgetHandle } from "../dom/registry";
import { dialogConfigForWidget } from "../state/widgetDialogConfig";
import type { DialogRendererData } from "../state/types";
import { emitSizesChange, emitUpdate } from "./events";

export interface LegacyCropDuster {
  /** Last-writer-wins global, as in 4.x; per-widget state is on the bridge. */
  mediaUrl: string;
  show(prefix: string, cropdusterUrl: string): void;
  complete(
    prefix: string,
    data: LegacyCompletePayload,
    rendererData?: DialogRendererData,
  ): void;
  setThumbnails(prefix: string, thumbs: Record<string, LegacyThumb>): void;
  createThumbnails(prefix: string): void;
  registerInput(input: Element | null): void;
  removeSize(prefix: string, sizeName: string): void;
  restoreSize(prefix: string, sizeName: string): void;
}

/** One removed size and its position, so `restoreSize` can put it back. */
interface RemovedSize {
  index: number;
  size: unknown;
}

const POPUP_FEATURES = "height=650,width=960,resizable=yes,scrollbars=yes";

/** 4.x parsed `location.search` once at load; re-reading it is equivalent. */
function getParams(): Record<string, string> {
  const data: Record<string, string> = {};
  for (const part of window.location.search.substring(1).split("&")) {
    const splits = part.split("=");
    if (splits.length <= 2) {
      data[splits[0] ?? ""] = decodeURIComponent(splits[1] ?? "");
    }
  }
  return data;
}

export function isDebug(): boolean {
  return getParams().cropduster_debug === "1";
}

/** jQuery's `.val()`: a multi-select yields its selected values. */
function elementValue(el: Element | null): string | undefined {
  if (!el) {
    return undefined;
  }
  if (el instanceof HTMLSelectElement && el.multiple) {
    return [...el.selectedOptions].map((option) => option.value).join(",");
  }
  if (
    el instanceof HTMLInputElement ||
    el instanceof HTMLTextAreaElement ||
    el instanceof HTMLSelectElement
  ) {
    return el.value;
  }
  return undefined;
}

/**
 * Open the 4.x upload popup.
 *
 * Preserve `encodeURI`, parameter order, the always-present `sizes` argument,
 * and the field-derived window name.
 *
 * A dialog opened this way returns its crop through
 * `window.opener.CropDuster.complete(el_id, ...)`, which resolves the field by
 * its prefix again. A row renamed while the popup is open can therefore receive
 * another row's result; the modal avoids that by retaining the widget element.
 */
export function openDialogWindow(prefix: string, cropdusterUrl: string): void {
  const data: Record<string, string | undefined> = {};
  for (const name of ["image", "id", "thumbs"]) {
    data[name] = elementValue(
      document.getElementById(`id_${prefix}-0-${name}`),
    );
  }
  data.sizes = JSON.stringify(
    readSizes(document.getElementById(`id_${prefix}`)),
  );

  let url = cropdusterUrl;
  for (const name of Object.keys(data)) {
    const value = data[name];
    if (value) {
      url += `&${name}=${encodeURI(value)}`;
    }
  }
  url += `&el_id=${encodeURI(prefix)}`;
  const windowName = String(prefix)
    .replace(/-/g, "____")
    .split(".")
    .join("___");
  if (isDebug()) {
    url += "&cropduster_debug=1";
  }
  window.open(url, windowName, POPUP_FEATURES)?.focus();
}

/**
 * The widget for a prefix, mounting one first if the markup was never adopted.
 *
 * `complete` and `setThumbnails` are called from outside on forms this bundle
 * may not have seen (hand-assembled markup, or a row inserted by a script that
 * emits no event we listen to), and they have to work there too.
 */
function resolveWidget(prefix: string): WidgetHandle | null {
  const existing = registry.byPrefix(prefix);
  if (existing) {
    return existing;
  }
  const root = rootForPrefix(prefix);
  if (!root) {
    return null;
  }
  registry.adopt(root);
  return registry.byRoot(root);
}

/**
 * A bridge for a prefix. Prefers a mounted widget's, which is connected to
 * its React tree; otherwise builds a throwaway one that only reads and
 * writes.
 */
function resolveBridge(prefix: string): FormsetBridge | null {
  const widget = resolveWidget(prefix);
  if (widget) {
    return widget.bridge;
  }
  const root = rootForPrefix(prefix);
  return root ? new FormsetBridge(root, { observe: false }) : null;
}

export function setThumbnails(
  prefix: string,
  thumbs: Record<string, LegacyThumb>,
): void {
  const bridge = resolveBridge(prefix);
  bridge?.setThumbOptions(thumbs);
  registry.byPrefix(prefix)?.refresh();
}

/** Re-render the thumbnail strip from the current formset state. */
export function createThumbnails(prefix: string): void {
  resolveWidget(prefix)?.refresh();
}

export function complete(
  prefix: string,
  data: LegacyCompletePayload,
  rendererData?: DialogRendererData,
): void {
  const bridge = resolveBridge(prefix);
  if (!bridge) {
    return;
  }
  if (!bridge.writeComplete(data, rendererData)) {
    return;
  }
  createThumbnails(prefix);
  emitUpdate(prefix, data);
}

/** Apply a modal result through the widget that opened it. */
export function completeWidget(
  widget: WidgetHandle,
  data: LegacyCompletePayload,
  rendererData?: DialogRendererData,
): void {
  if (!widget.bridge.writeComplete(data, rendererData)) {
    return;
  }
  widget.refresh();
  emitUpdate(widget.bridge.prefix ?? "", data);
}

/** Open a modal when requested; otherwise use the existing crop window. */
export function showWidget(
  widget: WidgetHandle | null,
  prefix: string,
  cropdusterUrl: string,
): void {
  if (widget?.config.dialogMode === "modal") {
    openModalDialog({
      config: dialogConfigForWidget(widget),
      // Retain the element so renaming its formset row cannot redirect the
      // completed crop.
      onComplete: (payload, rendererData) =>
        completeWidget(widget, payload, rendererData),
    });
    return;
  }
  openDialogWindow(prefix, cropdusterUrl);
}

/**
 * `CropDuster.show(prefix, url)`, as external callers know it.
 *
 * Resolve the prefix through `#id_{prefix}`, as in 4.x. `modal` opens in place;
 * the other modes retain the crop window.
 */
export function show(prefix: string, cropdusterUrl: string): void {
  showWidget(resolveWidget(prefix), prefix, cropdusterUrl);
}

/**
 * Adopt hand-built markup.
 *
 * 4.x bound a click handler here and ran at document ready over every
 * `.cropduster-data-field`, template rows included, so that `clone(true)`
 * would copy the handler into new rows. The custom element makes that
 * unnecessary; what remains is creating the element when a page's markup
 * predates it. Idempotent.
 */
export function registerInput(input: Element | null): void {
  const root = input?.closest<HTMLElement>(SELECTORS.form) ?? null;
  registry.adopt(root);
}

/**
 * Drop a size from a widget's size list.
 *
 * Splice the array returned by jQuery in place because downstream scripts
 * retain that object across size removals and restores.
 */
export function removeSize(prefix: string, sizeName: string): void {
  const field = document.getElementById(`id_${prefix}`);
  if (!field) {
    return;
  }
  const sizes = readSizes(field);
  let i = 0;
  for (; i < sizes.length; i++) {
    if (sizes[i]?.name === sizeName) {
      break;
    }
  }
  if (i === sizes.length) {
    return;
  }

  const removed = sizes.splice(i, 1);

  const stored = readData(field, "removedSizes");
  const removedSizes: Record<string, RemovedSize> =
    typeof stored === "object" && stored !== null
      ? (stored as Record<string, RemovedSize>)
      : {};
  // 4.x only wrote the map back when it was empty; the value is a live
  // object either way, so a single write keeps later mutations visible.
  if (Object.keys(removedSizes).length === 0) {
    writeData(field, "removedSizes", removedSizes);
  }
  removedSizes[sizeName] = { index: i, size: removed[0] };
  emitSizesChange(prefix);
}

/** Put a size removed by `removeSize` back where it was. */
export function restoreSize(prefix: string, sizeName: string): void {
  const field = document.getElementById(`id_${prefix}`);
  if (!field) {
    return;
  }
  const sizes = readSizes(field);
  const stored = readData(field, "removedSizes");
  const removedSizes =
    typeof stored === "object" && stored !== null
      ? (stored as Record<string, RemovedSize | undefined>)
      : null;
  const entry = removedSizes?.[sizeName];
  if (!entry) {
    return;
  }
  sizes.splice(entry.index, 0, entry.size as (typeof sizes)[number]);
  delete removedSizes[sizeName];
  emitSizesChange(prefix);
}

export const CropDuster: LegacyCropDuster = {
  mediaUrl: "",
  show,
  complete,
  setThumbnails,
  createThumbnails,
  registerInput,
  removeSize,
  restoreSize,
};

/** Publish the widget's media URL, last writer wins (as in 4.x). */
export function setMediaUrl(mediaUrl: string) {
  if (mediaUrl) {
    CropDuster.mediaUrl = mediaUrl;
  }
}

declare global {
  interface Window {
    CropDuster?: LegacyCropDuster;
  }
}

export function installGlobalApi(target: Window = window): LegacyCropDuster {
  target.CropDuster = CropDuster;
  return CropDuster;
}
