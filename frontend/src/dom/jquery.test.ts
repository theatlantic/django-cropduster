import { afterEach, describe, expect, it } from "vitest";
import jQuery from "jquery";

import {
  coerceDataValue,
  dataAttrName,
  jqueryInstances,
  readData,
  readSizes,
  triggerOnAll,
  writeData,
  writeSizesData,
} from "./jquery";

interface FakeCall {
  target: unknown;
  type: string;
  args: unknown[];
}

function fakeJQuery(log: FakeCall[] = []) {
  const $ = ((target: unknown) => ({
    data: () => undefined,
    trigger: (type: string, args: unknown[] = []) => {
      log.push({ target, type, args });
    },
  })) as unknown as { fn?: { jquery?: string } };
  $.fn = { jquery: "3.7.1" };
  return { $, log };
}

const globals = globalThis as unknown as Record<string, unknown>;

afterEach(() => {
  delete globals.django;
  delete globals.grp;
  delete globals.jQuery;
  delete globals.$;
  document.body.innerHTML = "";
});

describe("jqueryInstances", () => {
  it("finds django's copy first", () => {
    const a = fakeJQuery().$;
    const b = fakeJQuery().$;
    const c = fakeJQuery().$;
    globals.jQuery = c;
    globals.grp = { jQuery: b };
    globals.django = { jQuery: a };
    expect(jqueryInstances()).toEqual([a, b, c]);
  });

  it("deduplicates by identity", () => {
    const a = fakeJQuery().$;
    globals.django = { jQuery: a };
    globals.jQuery = a;
    globals.$ = a;
    expect(jqueryInstances()).toEqual([a]);
  });

  it("ignores things that are not jQuery", () => {
    globals.jQuery = () => undefined;
    globals.$ = {};
    expect(jqueryInstances()).toEqual([]);
  });
});

describe("data attribute mapping", () => {
  it("matches jQuery's camelCase to dashed conversion", () => {
    expect(dataAttrName("previewUrl")).toBe("data-preview-url");
    expect(dataAttrName("previewW")).toBe("data-preview-w");
    expect(dataAttrName("sizes")).toBe("data-sizes");
  });

  it("matches jQuery's value coercion", () => {
    expect(coerceDataValue("true")).toBe(true);
    expect(coerceDataValue("null")).toBe(null);
    expect(coerceDataValue("800")).toBe(800);
    expect(coerceDataValue("08")).toBe("08");
    expect(coerceDataValue('[{"name":"main"}]')).toEqual([{ name: "main" }]);
    expect(coerceDataValue("img/x.jpg")).toBe("img/x.jpg");
  });
});

describe("readSizes", () => {
  function input(sizes: string): HTMLInputElement {
    const el = document.createElement("input");
    el.setAttribute("data-sizes", sizes);
    document.body.appendChild(el);
    return el;
  }

  it("parses the attribute when there is no jQuery", () => {
    expect(readSizes(input('[{"name":"main"}]'))).toEqual([{ name: "main" }]);
  });

  it("keeps one array so in-place mutation is visible", () => {
    const el = input('[{"name":"main"},{"name":"thumb"}]');
    const first = readSizes(el);
    first.splice(0, 1);
    expect(readSizes(el)).toBe(first);
    expect(readSizes(el)).toHaveLength(1);
  });

  it("returns the array jQuery hands out, not a copy of the attribute", () => {
    const el = input('[{"name":"main"}]');
    globals.django = { jQuery };
    // What a downstream gallery script does on a layout change.
    const replacement = [{ name: "wide" }];
    jQuery(el).data("sizes", replacement);
    expect(readSizes(el)).toBe(replacement);
  });

  it("falls back to the attribute when jQuery holds no value", () => {
    const el = input('[{"name":"main"}]');
    globals.django = { jQuery };
    expect(readSizes(el)).toEqual([{ name: "main" }]);
  });

  it("is empty for a missing element", () => {
    expect(readSizes(null)).toEqual([]);
  });
});

describe("readData / writeData", () => {
  it("prefers the store over the attribute", () => {
    const el = document.createElement("input");
    el.setAttribute("data-preview-url", "/media/a.jpg");
    document.body.appendChild(el);
    expect(readData(el, "previewUrl")).toBe("/media/a.jpg");
    writeData(el, "previewUrl", "/media/b.jpg");
    expect(readData(el, "previewUrl")).toBe("/media/b.jpg");
    expect(el.getAttribute("data-preview-url")).toBe("/media/a.jpg");
  });

  it("writes through every jQuery instance", () => {
    const el = document.createElement("input");
    document.body.appendChild(el);
    globals.django = { jQuery };
    writeSizesData(el, [{ name: "main" }]);
    expect(jQuery(el).data("sizes")).toEqual([{ name: "main" }]);
  });
});

describe("triggerOnAll", () => {
  it("fires on every instance with positional arguments", () => {
    const log: FakeCall[] = [];
    const a = fakeJQuery(log).$;
    const b = fakeJQuery(log).$;
    globals.django = { jQuery: a };
    globals.grp = { jQuery: b };
    triggerOnAll(document, "cropduster:update", ["lead_image", { ok: true }]);
    expect(log).toHaveLength(2);
    expect(log[0]?.type).toBe("cropduster:update");
    expect(log[0]?.args).toEqual(["lead_image", { ok: true }]);
  });

  it("keeps going when one instance throws", () => {
    const log: FakeCall[] = [];
    const bad = (() => ({
      data: () => undefined,
      trigger: () => {
        throw new Error("boom");
      },
    })) as unknown as { fn?: { jquery?: string } };
    bad.fn = { jquery: "3.7.1" };
    globals.django = { jQuery: bad };
    globals.grp = { jQuery: fakeJQuery(log).$ };
    triggerOnAll(document, "cropduster:update", []);
    expect(log).toHaveLength(1);
  });
});
