/**
 * Read and write the server-rendered formset for one widget.
 *
 * django-nested-admin can rename or move a row, so each operation derives the
 * current prefix from the DOM and scopes name lookups to the widget root.
 * `writeComplete()` preserves the 4.x write order because downstream handlers
 * read the formset immediately afterward.
 */

import type { Size } from "../crop/geometry";
import { SELECTORS } from "../constants/classNames";
import { readData, readSizes, writeData } from "../dom/jquery";
import { observeValues } from "../dom/valueObserver";
import type { ValueObserver } from "../dom/valueObserver";
import type { LegacyCompletePayload, LegacyThumb } from "./legacyPayload";
import { derivePrefix, managementField } from "./naming";
import type { ManagementKey } from "./naming";

/** One selected `<option>` of the thumbs multi-select. */
export interface WidgetThumb {
  /** The option's value, i.e. the `Thumb` pk as a string. */
  id: string;
  /** The option's text, which is the raw size name. */
  name: string;
  width: number | null;
  height: number | null;
  url: string | null;
  /** `data-tmp-file`: the file is at its tmp path until the parent saves. */
  tmp: boolean;
}

/** The preview rendition `createThumbnails` draws. */
export interface WidgetPreview {
  url: string;
  width: string;
  height: string;
}

/** Values React reads from one widget's formset. */
export interface WidgetState {
  prefix: string | null;
  /** `-0-id`: the `cropduster.Image` pk, empty until one exists. */
  imageId: string;
  /** `-0-image`: the storage-relative name of the original. */
  origImage: string;
  /** The bare `{prefix}` field, which holds the same name. */
  value: string;
  thumbs: WidgetThumb[];
  deleted: boolean;
  preview: WidgetPreview;
}

export interface FormsetBridgeOptions {
  /**
   * Whether writes dispatch `input` and `change`. The 4.x code did not, so an
   * upload never marked the form dirty for admin-locking or autosave.
   */
  dispatchInputEvents?: boolean;
  /**
   * Whether to watch for external writes. A compatibility-only bridge can
   * disable observation when no widget is mounted.
   */
  observe?: boolean;
}

type FieldElement = HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement;

function escapeAttrValue(value: string): string {
  if (typeof CSS !== "undefined" && typeof CSS.escape === "function") {
    return CSS.escape(value);
  }
  return value.replace(/["\\]/g, "\\$&");
}

/** jQuery's `.val(v)` coercion: nullish becomes empty, numbers stringify. */
function toValue(value: unknown): string {
  if (value === null || value === undefined) {
    return "";
  }
  return typeof value === "string" ? value : String(value);
}

function toNumberOrNull(value: unknown): number | null {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const n = Number(value);
  return Number.isNaN(n) ? null : n;
}

function sameThumbs(a: WidgetThumb[], b: WidgetThumb[]): boolean {
  if (a.length !== b.length) {
    return false;
  }
  return a.every((thumb, i) => {
    const other = b[i];
    return (
      other !== undefined &&
      thumb.id === other.id &&
      thumb.name === other.name &&
      thumb.width === other.width &&
      thumb.height === other.height &&
      thumb.url === other.url &&
      thumb.tmp === other.tmp
    );
  });
}

function sameState(a: WidgetState, b: WidgetState): boolean {
  return (
    a.prefix === b.prefix &&
    a.imageId === b.imageId &&
    a.origImage === b.origImage &&
    a.value === b.value &&
    a.deleted === b.deleted &&
    a.preview.url === b.preview.url &&
    a.preview.width === b.preview.width &&
    a.preview.height === b.preview.height &&
    sameThumbs(a.thumbs, b.thumbs)
  );
}

export class FormsetBridge {
  readonly root: HTMLElement;

  #dispatchInputEvents: boolean;
  #observer: ValueObserver | null = null;
  #subscribers = new Set<(state: WidgetState) => void>();
  #snapshot: WidgetState;

  constructor(root: HTMLElement, options: FormsetBridgeOptions = {}) {
    this.root = root;
    this.#dispatchInputEvents = options.dispatchInputEvents !== false;
    this.#snapshot = this.readState();
    if (options.observe !== false) {
      this.#observer = observeValues(root, () => this.#notify());
    }
  }

  /** Re-derived on every access; a cached prefix goes stale on a rename. */
  get prefix(): string | null {
    return derivePrefix(this.root);
  }

  get dataField(): HTMLInputElement | null {
    return this.root.querySelector<HTMLInputElement>(SELECTORS.dataField);
  }

  /** The `{prefix}-0-{suffix}` field, or null while the row is a template. */
  field(suffix: string): FieldElement | null {
    const prefix = this.prefix;
    if (prefix === null) {
      return null;
    }
    return this.byName(`${prefix}-0-${suffix}`);
  }

  mgmt(key: ManagementKey): HTMLInputElement | null {
    const prefix = this.prefix;
    if (prefix === null) {
      return null;
    }
    return this.byName(managementField(prefix, key)) as HTMLInputElement | null;
  }

  byName(name: string): FieldElement | null {
    return this.root.querySelector<FieldElement>(
      `[name="${escapeAttrValue(name)}"]`,
    );
  }

  /** The size list, as the live array `removeSize` and downstream scripts
   * mutate. */
  readSizes(): Size[] {
    return readSizes(this.dataField);
  }

  get mediaUrl(): string {
    return toValue(readData(this.root, "mediaUrl"));
  }

  readState(): WidgetState {
    const dataField = this.dataField;
    const deleteField = this.field("DELETE");
    return {
      prefix: this.prefix,
      imageId: this.field("id")?.value ?? "",
      origImage: this.field("image")?.value ?? "",
      value: dataField?.value ?? "",
      thumbs: this.readThumbs(),
      deleted:
        deleteField instanceof HTMLInputElement ? deleteField.checked : false,
      preview: {
        url: toValue(readData(dataField, "previewUrl")),
        width: toValue(readData(dataField, "previewW")),
        height: toValue(readData(dataField, "previewH")),
      },
    };
  }

  /**
   * The selected thumb options, read the way `createThumbnails` read them:
   * the option's markup is the name and its `data-*` attributes store the
   * rendition.
   */
  readThumbs(): WidgetThumb[] {
    const select = this.field("thumbs");
    if (!(select instanceof HTMLSelectElement)) {
      return [];
    }
    const thumbs: WidgetThumb[] = [];
    for (const option of select.options) {
      if (!option.selected) {
        continue;
      }
      thumbs.push({
        id: option.value,
        name: option.innerHTML,
        width: toNumberOrNull(option.getAttribute("data-width")),
        height: toNumberOrNull(option.getAttribute("data-height")),
        url: option.getAttribute("data-url"),
        tmp: option.getAttribute("data-tmp-file") === "true",
      });
    }
    return thumbs;
  }

  /** The last computed state; stable by identity until something changes. */
  getSnapshot(): WidgetState {
    return this.#snapshot;
  }

  subscribe(callback: (state: WidgetState) => void): () => void {
    this.#subscribers.add(callback);
    return () => {
      this.#subscribers.delete(callback);
    };
  }

  /** Recompute now and notify if anything changed. */
  refresh() {
    this.#notify();
  }

  #notify() {
    const next = this.readState();
    if (sameState(this.#snapshot, next)) {
      return;
    }
    this.#snapshot = next;
    for (const callback of [...this.#subscribers]) {
      callback(next);
    }
  }

  /** Assign like jQuery's `.val()`, then dispatch the input events when
   * configured. */
  setValue(el: FieldElement | null, value: unknown) {
    if (!el) {
      return;
    }
    el.value = toValue(value);
    if (this.#dispatchInputEvents) {
      el.dispatchEvent(new Event("input", { bubbles: true }));
      el.dispatchEvent(new Event("change", { bubbles: true }));
    }
  }

  /**
   * `CropDuster.complete`'s DOM writes, in its order.
   *
   * Downstream code depends on the order: handlers write `-0-attribution`
   * as soon as this returns, and the `INITIAL_FORMS` reset is conditional on
   * the value just written to `-0-id`. Returns false when 4.x would have
   * returned early, leaving the thumbnails and the event to the caller.
   */
  writeComplete(data: LegacyCompletePayload): boolean {
    const run = () => {
      const crop = data.crop;
      const idField = this.field("id");
      this.setValue(idField, crop?.image_id);
      if (idField && idField.value === "") {
        this.setValue(this.mgmt("INITIAL_FORMS"), "0");
      }
      this.setValue(this.field("image"), crop?.orig_image);
      this.setValue(this.dataField, crop?.orig_image);
      this.setValue(this.mgmt("TOTAL_FORMS"), "1");
      // Preserve the 4.x `typeof null === "object"` branch.
      if (typeof data.thumbs !== "object") {
        return false;
      }
      this.setThumbOptions(crop?.thumbs ?? {});
      const dataField = this.dataField;
      writeData(dataField, "previewUrl", data.preview_url);
      writeData(dataField, "previewW", data.preview_w);
      writeData(dataField, "previewH", data.preview_h);
      return true;
    };

    const observer = this.#observer;
    const wrote = observer ? observer.suppress(run) : run();
    this.#notify();
    return wrote;
  }

  /**
   * Rebuild the thumbs multi-select.
   *
   * The attributes are the ones both `CropDuster.setThumbnails` and the
   * server widget emit, because `createThumbnails` and downstream admin
   * scripts read them back from the options.
   */
  setThumbOptions(thumbs: Record<string, LegacyThumb>) {
    const select = this.field("thumbs");
    if (!(select instanceof HTMLSelectElement)) {
      return;
    }
    const write = () => {
      for (const option of [...select.querySelectorAll("option")]) {
        option.remove();
      }
      for (const name of Object.keys(thumbs)) {
        const thumb = thumbs[name];
        if (!thumb?.id) {
          continue;
        }
        const option = select.ownerDocument.createElement("option");
        option.innerHTML = toValue(thumb.name);
        setOptionAttr(option, "value", thumb.id);
        setOptionAttr(option, "data-width", thumb.width);
        setOptionAttr(option, "data-height", thumb.height);
        setOptionAttr(option, "data-url", thumb.url);
        option.setAttribute("data-tmp-file", "true");
        option.setAttribute("selected", "selected");
        select.appendChild(option);
      }
    };
    const observer = this.#observer;
    if (observer) {
      observer.suppress(write);
    } else {
      write();
    }
  }

  destroy() {
    this.#observer?.destroy();
    this.#observer = null;
    this.#subscribers.clear();
  }
}

/** jQuery's `.attr()` setter: undefined is a no-op, null removes. */
function setOptionAttr(
  option: HTMLOptionElement,
  name: string,
  value: unknown,
) {
  if (value === undefined) {
    return;
  }
  if (value === null) {
    option.removeAttribute(name);
    return;
  }
  option.setAttribute(name, String(value));
}
