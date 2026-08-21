/**
 * Watch server-rendered form controls changed without an input event.
 *
 * jQuery `.val()`, direct `checked` or `selected` assignments, option
 * replacement, and django-autosave recreation bypass ordinary listeners.
 * Per-element setters, a MutationObserver, and input/change listeners schedule
 * one callback per animation frame. Prototype accessors are never modified.
 */

/** Attributes that can change a field lookup or thumbnail value. */
export const OBSERVED_ATTRIBUTES = [
  "id",
  "name",
  "value",
  "selected",
  "data-url",
  "data-width",
  "data-height",
] as const;

const VALUE_HOSTS = "input,select,textarea,option";

type ValueElement =
  | HTMLInputElement
  | HTMLSelectElement
  | HTMLTextAreaElement
  | HTMLOptionElement;
type ObservedProperty = "value" | "checked" | "selected";

export interface ValueObserver {
  /** Reinstall accessors on the current children (idempotent). */
  refresh(): void;
  /** Run a pending notification immediately. */
  flush(): void;
  /** Run `fn` with our own property writes not counting as external changes. */
  suppress<T>(fn: () => T): T;
  destroy(): void;
}

function prototypeDescriptor(
  el: Element,
  prop: ObservedProperty,
): PropertyDescriptor | undefined {
  let proto: object | null = Object.getPrototypeOf(el) as object | null;
  while (proto) {
    const descriptor = Object.getOwnPropertyDescriptor(proto, prop);
    if (descriptor) {
      return descriptor;
    }
    proto = Object.getPrototypeOf(proto) as object | null;
  }
  return undefined;
}

/**
 * Observe every form control under `root`, calling `notify` (debounced) when
 * one of them changes by any route.
 */
export function observeValues(
  root: HTMLElement,
  notify: () => void,
): ValueObserver {
  const shimmed = new Map<
    Element,
    Map<ObservedProperty, PropertyDescriptor | undefined>
  >();
  let suppressed = false;
  let frame: number | null = null;
  let destroyed = false;

  const schedule = () => {
    if (destroyed || suppressed || frame !== null) {
      return;
    }
    frame = requestFrame(() => {
      frame = null;
      notify();
    });
  };

  const install = (
    el: Element,
    prop: ObservedProperty,
    originals: Map<ObservedProperty, PropertyDescriptor | undefined>,
  ) => {
    const descriptor = prototypeDescriptor(el, prop);
    const get = descriptor?.get;
    const set = descriptor?.set;
    if (!get || !set) {
      return;
    }
    originals.set(prop, Object.getOwnPropertyDescriptor(el, prop));
    Object.defineProperty(el, prop, {
      configurable: true,
      enumerable: descriptor?.enumerable ?? true,
      get(this: Element) {
        return get.call(this) as unknown;
      },
      set(this: Element, next: unknown) {
        set.call(this, next);
        if (!suppressed) {
          schedule();
        }
      },
    });
  };

  const restore = (el: Element) => {
    const originals = shimmed.get(el);
    if (!originals) {
      return;
    }
    for (const [prop, descriptor] of originals) {
      if (descriptor) {
        Object.defineProperty(el, prop, descriptor);
      } else {
        Reflect.deleteProperty(el, prop);
      }
    }
    shimmed.delete(el);
  };

  const refresh = () => {
    if (destroyed) {
      return;
    }
    for (const el of root.querySelectorAll<ValueElement>(VALUE_HOSTS)) {
      if (shimmed.has(el)) {
        continue;
      }
      const originals = new Map<
        ObservedProperty,
        PropertyDescriptor | undefined
      >();
      if (el instanceof HTMLOptionElement) {
        install(el, "selected", originals);
      } else {
        install(el, "value", originals);
        if (el instanceof HTMLInputElement) {
          install(el, "checked", originals);
        }
      }
      if (originals.size) {
        shimmed.set(el, originals);
      }
    }
    for (const el of [...shimmed.keys()]) {
      if (!root.contains(el)) {
        restore(el);
      }
    }
  };

  const observer = new MutationObserver((records) => {
    let structural = false;
    for (const record of records) {
      if (record.type === "childList") {
        structural = true;
        break;
      }
    }
    if (structural) {
      refresh();
    }
    schedule();
  });

  observer.observe(root, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: [...OBSERVED_ATTRIBUTES],
  });

  root.addEventListener("change", schedule, true);
  root.addEventListener("input", schedule, true);

  refresh();

  return {
    refresh,
    flush() {
      if (frame !== null) {
        cancelFrame(frame);
        frame = null;
        notify();
      }
    },
    suppress<T>(fn: () => T): T {
      const previous = suppressed;
      if (!previous && observer.takeRecords().length) {
        schedule();
      }
      suppressed = true;
      try {
        return fn();
      } finally {
        if (!previous) {
          observer.takeRecords();
        }
        suppressed = previous;
        if (!previous) {
          refresh();
        }
      }
    },
    destroy() {
      destroyed = true;
      if (frame !== null) {
        cancelFrame(frame);
        frame = null;
      }
      observer.disconnect();
      root.removeEventListener("change", schedule, true);
      root.removeEventListener("input", schedule, true);
      for (const el of [...shimmed.keys()]) {
        restore(el);
      }
    },
  };
}

function requestFrame(callback: () => void): number {
  if (typeof requestAnimationFrame === "function") {
    return requestAnimationFrame(callback);
  }
  return setTimeout(callback, 0) as unknown as number;
}

function cancelFrame(handle: number) {
  if (typeof cancelAnimationFrame === "function") {
    cancelAnimationFrame(handle);
    return;
  }
  clearTimeout(handle);
}
