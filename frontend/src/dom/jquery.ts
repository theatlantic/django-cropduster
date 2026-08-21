/**
 * Compatibility access to jQuery data and events.
 *
 * Existing pages may store sizes and preview values in `django.jQuery`,
 * `grp.jQuery`, or a global jQuery instance. Reads use the first instance with
 * a value; writes and events go to each distinct instance. A local WeakMap
 * preserves the mutable sizes array when no jQuery is present.
 */

import type { Size } from "../crop/geometry";

export interface JQueryObjectLike {
  data(key: string): unknown;
  data(key: string, value: unknown): unknown;
  trigger(type: string, extraParameters?: unknown[]): unknown;
}

export interface JQueryLike {
  (target: unknown): JQueryObjectLike;
  fn?: { jquery?: string };
}

interface JQueryGlobals {
  django?: { jQuery?: unknown };
  grp?: { jQuery?: unknown };
  jQuery?: unknown;
  $?: unknown;
}

function isJQuery(candidate: unknown): candidate is JQueryLike {
  return (
    typeof candidate === "function" &&
    typeof (candidate as JQueryLike).fn?.jquery === "string"
  );
}

/**
 * Every distinct jQuery on the page, django's first.
 *
 * Deduplicated by function identity: on a page where `window.jQuery` *is*
 * `django.jQuery` an event must fire once, not twice.
 */
export function jqueryInstances(): JQueryLike[] {
  const globals = globalThis as unknown as JQueryGlobals;
  const found = new Set<JQueryLike>();
  for (const candidate of [
    globals.django?.jQuery,
    globals.grp?.jQuery,
    globals.jQuery,
    globals.$,
  ]) {
    if (isJQuery(candidate)) {
      found.add(candidate);
    }
  }
  return [...found];
}

/** Local data store for pages without jQuery. */
const localStore = new WeakMap<object, Map<string, unknown>>();

function localData(target: object): Map<string, unknown> {
  let store = localStore.get(target);
  if (!store) {
    store = new Map();
    localStore.set(target, store);
  }
  return store;
}

const RBRACE = /^(?:\{[\w\W]*\}|\[[\w\W]*\])$/;

/** jQuery's `data-*` attribute name for a data key. */
export function dataAttrName(key: string): string {
  return `data-${key.replace(/[A-Z]/g, "-$&").toLowerCase()}`;
}

/** jQuery's `dataAttr` coercion of an attribute value. */
export function coerceDataValue(value: string): unknown {
  if (value === "true") {
    return true;
  }
  if (value === "false") {
    return false;
  }
  if (value === "null") {
    return null;
  }
  if (+value + "" === value) {
    return +value;
  }
  if (RBRACE.test(value)) {
    try {
      return JSON.parse(value) as unknown;
    } catch {
      return value;
    }
  }
  return value;
}

function attrData(el: Element, key: string): unknown {
  const raw = el.getAttribute(dataAttrName(key));
  return raw === null ? undefined : coerceDataValue(raw);
}

/**
 * `$(el).data(key)`, through whichever jQuery holds a value, falling back to
 * the local store and then to the `data-*` attribute.
 */
export function readData(el: Element | null, key: string): unknown {
  if (!el) {
    return undefined;
  }
  for (const $ of jqueryInstances()) {
    const value = $(el).data(key);
    if (value !== undefined) {
      return value;
    }
  }
  const store = localStore.get(el);
  if (store?.has(key)) {
    return store.get(key);
  }
  return attrData(el, key);
}

/** `$(el).data(key, value)` on every jQuery instance, and locally. */
export function writeData(el: Element | null, key: string, value: unknown) {
  if (!el) {
    return;
  }
  for (const $ of jqueryInstances()) {
    $(el).data(key, value);
  }
  localData(el).set(key, value);
}

/**
 * The size list for a data field, as the array every other consumer holds.
 *
 * `removeSize`/`restoreSize` work by mutating the result, so the array is
 * never copied and never cached anywhere but the data store it came from.
 */
export function readSizes(dataField: Element | null): Size[] {
  if (!dataField) {
    return [];
  }
  for (const $ of jqueryInstances()) {
    const value = $(dataField).data("sizes");
    if (Array.isArray(value)) {
      return value as Size[];
    }
  }
  const store = localData(dataField);
  const local = store.get("sizes");
  if (Array.isArray(local)) {
    return local as Size[];
  }
  const parsed = attrData(dataField, "sizes");
  const sizes = Array.isArray(parsed) ? (parsed as Size[]) : [];
  store.set("sizes", sizes);
  return sizes;
}

/** Publish a size list under `sizes`, keeping one array shared by everyone. */
export function writeSizesData(dataField: Element | null, sizes: Size[]) {
  writeData(dataField, "sizes", sizes);
}

/** Fire a jQuery event with 4.x's positional arguments on every instance. */
export function triggerOnAll(
  target: unknown,
  type: string,
  args: unknown[] = [],
) {
  for (const $ of jqueryInstances()) {
    try {
      $(target).trigger(type, args);
    } catch {
      // A handler on one instance must not stop the others from running.
    }
  }
}

/** Bind a jQuery event on every instance; returns an unbind function. */
export function onAll(
  target: unknown,
  type: string,
  handler: (...args: unknown[]) => void,
): () => void {
  const bound: JQueryLike[] = [];
  for (const $ of jqueryInstances()) {
    const obj = $(target) as JQueryObjectLike & {
      on?: (type: string, handler: (...args: unknown[]) => void) => unknown;
      off?: (type: string, handler: (...args: unknown[]) => void) => unknown;
    };
    if (typeof obj.on === "function") {
      obj.on(type, handler);
      bound.push($);
    }
  }
  return () => {
    for (const $ of bound) {
      const obj = $(target) as JQueryObjectLike & {
        off?: (type: string, handler: (...args: unknown[]) => void) => unknown;
      };
      obj.off?.(type, handler);
    }
  };
}
