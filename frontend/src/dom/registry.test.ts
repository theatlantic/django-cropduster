import { afterEach, beforeAll, describe, expect, it } from "vitest";

import { defineWidgetElement } from "./CropDusterWidgetElement";
import { registry, rootForPrefix } from "./registry";
import { cleanupDocument, flush, mountFixture } from "../testing/fixtures";

beforeAll(() => {
  defineWidgetElement();
});

afterEach(cleanupDocument);

describe("byPrefix", () => {
  it("resolves through #id_{prefix} and its .cropduster-form", async () => {
    const a = mountFixture({ prefix: "photo_set-0-image" });
    const b = mountFixture({ prefix: "photo_set-1-image" });
    await flush(0);

    expect(registry.byPrefix("photo_set-0-image")?.root).toBe(a.root);
    expect(registry.byPrefix("photo_set-1-image")?.root).toBe(b.root);
    expect(registry.byPrefix("photo_set-2-image")).toBeNull();
  });

  it("follows a renamed row", async () => {
    const fixture = mountFixture({ prefix: "photo_set-0-image" });
    await flush(0);
    const widget = registry.byPrefix("photo_set-0-image");

    for (const el of fixture.root.querySelectorAll("[id],[name]")) {
      for (const attribute of ["id", "name"]) {
        const value = el.getAttribute(attribute);
        if (value) {
          el.setAttribute(
            attribute,
            value.replace("photo_set-0-", "photo_set-9-"),
          );
        }
      }
    }

    expect(registry.byPrefix("photo_set-0-image")).toBeNull();
    expect(registry.byPrefix("photo_set-9-image")).toBe(widget);
  });

  it("returns null when the field is not in a widget", () => {
    document.body.innerHTML = '<input id="id_orphan" name="orphan">';
    expect(rootForPrefix("orphan")).toBeNull();
    expect(registry.byPrefix("orphan")).toBeNull();
  });
});

describe("adopt", () => {
  it("creates the element for markup that predates it", async () => {
    const fixture = mountFixture({ withElement: false });
    expect(fixture.root.querySelectorAll("cropduster-widget")).toHaveLength(0);

    registry.adopt(fixture.root);
    await flush(0);

    const hosts = fixture.root.querySelectorAll("cropduster-widget");
    expect(hosts).toHaveLength(1);
    expect(hosts[0]?.previousElementSibling).toBe(fixture.dataField);
    expect(registry.byPrefix("lead_image")?.root).toBe(fixture.root);
  });

  it("is idempotent", async () => {
    const fixture = mountFixture({ withElement: false });
    registry.adopt(fixture.root);
    registry.adopt(fixture.root);
    await flush(0);
    registry.adopt(fixture.root);
    await flush(0);

    expect(fixture.root.querySelectorAll("cropduster-widget")).toHaveLength(1);
  });

  it("ignores a form with no data field", () => {
    const root = document.createElement("div");
    root.className = "cropduster-form";
    document.body.appendChild(root);
    registry.adopt(root);
    expect(root.querySelectorAll("cropduster-widget")).toHaveLength(0);
  });
});

describe("rescan", () => {
  it("mounts everything and stays idempotent", async () => {
    mountFixture({ prefix: "a_image", withElement: false });
    mountFixture({ prefix: "b_image" });
    mountFixture({ prefix: "photo_set-__prefix__-image" });

    registry.rescan();
    await flush(0);
    registry.rescan();
    await flush(0);

    expect(registry.byPrefix("a_image")).not.toBeNull();
    expect(registry.byPrefix("b_image")).not.toBeNull();
    expect(registry.byPrefix("photo_set-__prefix__-image")).toBeNull();
    expect(document.querySelectorAll("cropduster-widget")).toHaveLength(3);
  });
});
