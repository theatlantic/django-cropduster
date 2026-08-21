import { afterEach, beforeAll, describe, expect, it } from "vitest";

import {
  CropDusterWidgetElement,
  defineWidgetElement,
} from "./CropDusterWidgetElement";
import { registry } from "./registry";
import {
  cleanupDocument,
  flush,
  mountFixture,
  widgetHtml,
} from "../testing/fixtures";

beforeAll(() => {
  defineWidgetElement();
});

afterEach(cleanupDocument);

function host(scope: ParentNode): CropDusterWidgetElement {
  const el = scope.querySelector("cropduster-widget");
  if (!(el instanceof CropDusterWidgetElement)) {
    throw new Error("element did not upgrade");
  }
  return el;
}

/** nested-admin's rename: `__prefix__` becomes the new row index. */
function rename(scope: ParentNode, index: string) {
  for (const el of scope.querySelectorAll("[id],[name]")) {
    for (const attribute of ["id", "name"]) {
      const value = el.getAttribute(attribute);
      if (value?.includes("__prefix__")) {
        el.setAttribute(attribute, value.replace("__prefix__", index));
      }
    }
  }
}

describe("mounting", () => {
  it("mounts a real row one microtask after insertion", async () => {
    const fixture = mountFixture({ prefix: "lead_image" });
    expect(registry.byPrefix("lead_image")).toBeNull();

    await flush(0);

    const widget = registry.byPrefix("lead_image");
    expect(widget).not.toBeNull();
    expect(widget?.root).toBe(fixture.root);
    expect(host(fixture.container).widget).toBe(widget);
  });

  it("never mounts an empty-form template", async () => {
    const fixture = mountFixture({ prefix: "photo_set-__prefix__-image" });
    await flush(0);

    expect(host(fixture.container).widget).toBeNull();
    expect(registry.byPrefix("photo_set-__prefix__-image")).toBeNull();
  });

  it("mounts a cloned template once it has been renamed", async () => {
    const template = document.createElement("div");
    template.innerHTML = widgetHtml({ prefix: "photo_set-__prefix__-image" });
    document.body.appendChild(template);
    await flush(0);

    // add(): clone the template, rename it, then insert it.
    const row = template.firstElementChild!.cloneNode(true) as HTMLElement;
    rename(row, "3");
    document.body.appendChild(row);
    await flush(0);

    const widget = registry.byPrefix("photo_set-3-image");
    expect(widget).not.toBeNull();
    expect(row.contains(widget!.root)).toBe(true);
    expect(host(template).widget).toBeNull();
  });

  it("mounts when the rename happens after the insertion", async () => {
    const template = document.createElement("div");
    template.innerHTML = widgetHtml({ prefix: "photo_set-__prefix__-image" });
    document.body.appendChild(template);

    const row = template.firstElementChild!.cloneNode(true) as HTMLElement;
    document.body.appendChild(row);
    await flush(0);
    expect(registry.byPrefix("photo_set-4-image")).toBeNull();

    rename(row, "4");
    await flush(0);

    expect(registry.byPrefix("photo_set-4-image")).not.toBeNull();
  });
});

describe("teardown", () => {
  it("survives a detach and re-attach in the same task", async () => {
    const fixture = mountFixture({ prefix: "lead_image" });
    await flush(0);
    const widget = registry.byPrefix("lead_image");

    // jQuery-UI sortable, and nested-admin's cross-group splice.
    const parent = fixture.root.parentElement!;
    fixture.root.remove();
    parent.appendChild(fixture.root);

    await flush(5);
    expect(registry.byPrefix("lead_image")).toBe(widget);
    expect(host(fixture.container).widget).toBe(widget);
  });

  it("mounts a row renamed while it was detached", async () => {
    const template = document.createElement("div");
    template.innerHTML = widgetHtml({ prefix: "photo_set-__prefix__-image" });
    document.body.appendChild(template);
    const row = template.firstElementChild!.cloneNode(true) as HTMLElement;
    document.body.appendChild(row);
    await flush(0);

    row.remove();
    rename(row, "5");
    document.body.appendChild(row);
    await flush(5);

    expect(registry.byPrefix("photo_set-5-image")).not.toBeNull();
  });

  it("tears down a row that stays detached", async () => {
    const fixture = mountFixture({ prefix: "lead_image" });
    await flush(0);
    const element = host(fixture.container);

    fixture.root.remove();
    await flush(5);

    expect(element.widget).toBeNull();
    expect(registry.byPrefix("lead_image")).toBeNull();
  });
});
