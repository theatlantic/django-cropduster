/**
 * Record formset writes synchronously and in order.
 *
 * Assigning DOM properties emits no event, while MutationObserver callbacks
 * run after `CropDuster.complete()` has finished. The wrapped accessors
 * preserve the interleaving that downstream handlers depend on.
 */

type ValueElement = HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement;

const VALUE_HOSTS = "input,select,textarea";

export interface WriteLog {
  /** The writes so far, in order, oldest first. */
  entries: string[];
  clear(): void;
  stop(): void;
}

function accessor(
  el: Element,
  prop: "value" | "checked",
): PropertyDescriptor | undefined {
  let target: object | null = el;
  while (target) {
    const descriptor = Object.getOwnPropertyDescriptor(target, prop);
    if (descriptor) {
      return descriptor;
    }
    target = Object.getPrototypeOf(target) as object | null;
  }
  return undefined;
}

function label(el: Element): string {
  return el.getAttribute("name") || el.id || el.tagName.toLowerCase();
}

/** Record every value, checked and option write under `root`. */
export function recordWrites(root: HTMLElement): WriteLog {
  const entries: string[] = [];
  const restore: (() => void)[] = [];

  const wrapAccessor = (el: Element, prop: "value" | "checked") => {
    const descriptor = accessor(el, prop);
    const get = descriptor?.get;
    const set = descriptor?.set;
    if (!get || !set) {
      return;
    }
    const previous = Object.getOwnPropertyDescriptor(el, prop);
    Object.defineProperty(el, prop, {
      configurable: true,
      enumerable: descriptor.enumerable ?? true,
      get(this: Element) {
        return get.call(this) as unknown;
      },
      set(this: Element, next: unknown) {
        entries.push(`${prop} ${label(el)}=${String(next)}`);
        set.call(this, next);
      },
    });
    restore.push(() => {
      if (previous) {
        Object.defineProperty(el, prop, previous);
      } else {
        Reflect.deleteProperty(el, prop);
      }
    });
  };

  const wrapOption = (option: HTMLOptionElement) => {
    const original = option.remove.bind(option);
    Object.defineProperty(option, "remove", {
      configurable: true,
      writable: true,
      value: () => {
        entries.push(`option -${option.value}`);
        original();
      },
    });
  };

  const wrapSelect = (select: HTMLSelectElement) => {
    const original = select.appendChild;
    Object.defineProperty(select, "appendChild", {
      configurable: true,
      writable: true,
      value: function <T extends Node>(this: HTMLSelectElement, node: T): T {
        if (node instanceof HTMLOptionElement) {
          entries.push(`option +${node.value}`);
          wrapOption(node);
        }
        return original.call(this, node) as T;
      },
    });
    restore.push(() => {
      Reflect.deleteProperty(select, "appendChild");
    });
    for (const option of select.options) {
      wrapOption(option);
    }
  };

  for (const el of root.querySelectorAll<ValueElement>(VALUE_HOSTS)) {
    wrapAccessor(el, "value");
    if (el instanceof HTMLInputElement) {
      wrapAccessor(el, "checked");
    }
    if (el instanceof HTMLSelectElement) {
      wrapSelect(el);
    }
  }

  return {
    entries,
    clear() {
      entries.length = 0;
    },
    stop() {
      for (const undo of restore.splice(0)) {
        undo();
      }
    },
  };
}
