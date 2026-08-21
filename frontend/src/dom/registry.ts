/**
 * Track mounted widgets by element.
 *
 * Prefixes change when django-nested-admin renames a row, so `byPrefix()`
 * resolves the current data field before finding its widget.
 */

import { SELECTORS, WIDGET_TAG } from "../constants/classNames";
import type { FormsetBridge } from "../formset/FormsetBridge";
import type { WidgetConfig } from "./config";

/** What a mounted widget offers the compatibility layer. */
export interface WidgetHandle {
  /** The `.cropduster-form` wrapper. */
  readonly root: HTMLElement;
  /** The `<cropduster-widget>` element React is rooted on. */
  readonly host: HTMLElement;
  readonly bridge: FormsetBridge;
  readonly config: WidgetConfig;
  /** Re-read the formset and re-render. */
  refresh(): void;
  destroy(): void;
}

/** A `<cropduster-widget>` that can re-attempt its mount on demand. */
interface MountableHost extends HTMLElement {
  tryMount(): void;
}

function isMountable(el: Element): el is MountableHost {
  return typeof (el as MountableHost).tryMount === "function";
}

class WidgetRegistry {
  #widgets = new Map<Element, WidgetHandle>();

  add(handle: WidgetHandle) {
    this.#widgets.set(handle.host, handle);
  }

  remove(handle: WidgetHandle | null | undefined) {
    if (handle) {
      this.#widgets.delete(handle.host);
    }
  }

  get(host: Element | null | undefined): WidgetHandle | null {
    return (host && this.#widgets.get(host)) || null;
  }

  all(): WidgetHandle[] {
    return [...this.#widgets.values()];
  }

  byRoot(root: Element | null | undefined): WidgetHandle | null {
    if (!root) {
      return null;
    }
    for (const handle of this.#widgets.values()) {
      if (handle.root === root) {
        return handle;
      }
    }
    return null;
  }

  /** 4.x resolution: the widget whose form contains `#id_{prefix}`. */
  byPrefix(prefix: string): WidgetHandle | null {
    return this.byRoot(rootForPrefix(prefix));
  }

  /**
   * Mount anything that is not mounted yet.
   *
   * The custom element is the normal mount path. A rescan also adopts markup
   * built before 5.0, which has no `<cropduster-widget>`.
   */
  rescan(scope: ParentNode = document) {
    for (const el of scope.querySelectorAll(WIDGET_TAG)) {
      if (isMountable(el)) {
        el.tryMount();
      }
    }
    for (const root of scope.querySelectorAll<HTMLElement>(SELECTORS.form)) {
      this.adopt(root);
    }
  }

  /**
   * Ensure a `.cropduster-form` has a widget element, creating one if the
   * markup predates 5.0. Mounting itself is the element's job.
   */
  adopt(root: HTMLElement | null): void {
    if (!root) {
      return;
    }
    const existing = root.querySelector(WIDGET_TAG);
    if (existing) {
      if (isMountable(existing)) {
        existing.tryMount();
      }
      return;
    }
    const dataField = root.querySelector(SELECTORS.dataField);
    if (!dataField) {
      return;
    }
    const host = root.ownerDocument.createElement(WIDGET_TAG);
    dataField.after(host);
  }
}

/** `#id_{prefix}` up to its `.cropduster-form`, as 4.x looked widgets up. */
export function rootForPrefix(prefix: string): HTMLElement | null {
  const field = document.getElementById(`id_${prefix}`);
  return field?.closest<HTMLElement>(SELECTORS.form) ?? null;
}

export const registry = new WidgetRegistry();
