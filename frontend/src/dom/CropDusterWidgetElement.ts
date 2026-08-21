/**
 * Mount a widget when a real formset row enters the document.
 *
 * The element waits for django-nested-admin to replace template prefixes and
 * for the parser to add the portal containers. Its attributes cannot contain
 * a formset prefix because nested-admin does not rewrite this tag. Brief
 * detach/reinsert operations defer teardown until the next task.
 */

import { WIDGET_TAG, SELECTORS } from "../constants/classNames";
import { derivePrefix, isTemplatePrefix } from "../formset/naming";
import { setMediaUrl } from "../compat/globalApi";
import { readConfig } from "./config";
import { registry } from "./registry";
import { hasSlots, WidgetInstance } from "./WidgetInstance";

export class CropDusterWidgetElement extends HTMLElement {
  #widget: WidgetInstance | null = null;
  #pending: MutationObserver | null = null;
  #teardown: number | null = null;

  connectedCallback() {
    if (this.#teardown !== null) {
      // A detach/re-attach (a sortable drag, or a splice into another group):
      // the teardown that was queued for it never has to happen.
      clearTimeout(this.#teardown);
      this.#teardown = null;
      if (this.#widget) {
        return;
      }
    }
    // Let the caller finish assigning the cloned row's formset prefix.
    queueMicrotask(() => this.tryMount());
  }

  /**
   * Mount if the row is real and not already mounted.
   *
   * Public so formset event handlers can retry the same idempotent mount.
   */
  tryMount() {
    if (!this.isConnected || this.#widget) {
      return;
    }
    const root = this.closest<HTMLElement>(SELECTORS.form);
    if (!root) {
      return;
    }
    const prefix = derivePrefix(root);
    if (prefix === null || isTemplatePrefix(prefix)) {
      // An empty-form template. It becomes a real row by being renamed, which
      // may happen after it is inserted, so watch for that and try again.
      this.#watchRoot(root);
      return;
    }
    if (document.readyState === "loading" && !hasSlots(root)) {
      // The parser has not reached the two portal containers yet.
      this.#watchRoot(root);
      return;
    }
    this.#pending?.disconnect();
    this.#pending = null;

    this.#widget = new WidgetInstance(root, this, readConfig(this));
    registry.add(this.#widget);
    setMediaUrl(this.#widget.mediaUrl);
  }

  /**
   * Retry the mount when the row changes.
   *
   * Covers both reasons a row can be unmountable: a template prefix that a
   * rename will replace, and a row the parser has not finished writing.
   */
  #watchRoot(root: HTMLElement) {
    if (this.#pending) {
      return;
    }
    this.#pending = new MutationObserver(() => this.tryMount());
    this.#pending.observe(root, {
      childList: true,
      attributes: true,
      subtree: true,
      attributeFilter: ["name", "id"],
    });
  }

  disconnectedCallback() {
    if (this.#teardown !== null) {
      return;
    }
    // jQuery-UI sortable and cross-group splices both detach the row and put
    // it back in the same task. Tearing React down synchronously would throw
    // away a widget that is only moving.
    this.#teardown = window.setTimeout(() => {
      this.#teardown = null;
      if (this.isConnected) {
        return;
      }
      this.#pending?.disconnect();
      this.#pending = null;
      this.#widget?.destroy();
      this.#widget = null;
    }, 0);
  }

  /** The mounted widget, or null while this is a template row. */
  get widget(): WidgetInstance | null {
    return this.#widget;
  }
}

/** Register the element. Idempotent, and a no-op without custom elements. */
export function defineWidgetElement(tag: string = WIDGET_TAG) {
  if (typeof customElements === "undefined" || customElements.get(tag)) {
    return;
  }
  customElements.define(tag, CropDusterWidgetElement);
}
