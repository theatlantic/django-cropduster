import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { afterAll, beforeAll, describe, expect, it } from "vitest";

import {
  cleanupDocument,
  isWidgetMounted,
  waitFor,
} from "../src/testing/fixtures";
import { fixtureHtml } from "../src/testing/htmlFixtures";

const DIST = resolve(
  dirname(fileURLToPath(import.meta.url)),
  "../../cropduster/static/cropduster/dist",
);

const read = (name: string) => readFileSync(resolve(DIST, name), "utf8");

beforeAll(async () => {
  document.body.innerHTML =
    fixtureHtml("article_change_lead_and_alt") +
    fixtureHtml("nested_empty_item");

  (0, eval)(read("cropduster.js"));
  document.dispatchEvent(new Event("DOMContentLoaded"));
  await waitFor(
    () =>
      ["lead_image", "alt_image"].every((prefix) =>
        isWidgetMounted(document.getElementById(`${prefix}-group`)!),
      ),
    { message: "the built bundle to mount both widgets" },
  );
});

afterAll(cleanupDocument);

describe("the widget bundle", () => {
  it("is one file with no runtime chunks", () => {
    const source = read("cropduster.js");
    expect(source).not.toMatch(/\bimport\s*\(/);
    expect(source).not.toContain("import.meta");
    expect(source).toContain("//# sourceMappingURL=cropduster.js.map");
  });

  it("ships CSS with no unresolved asset URLs", () => {
    const css = read("cropduster.css");
    expect(css).toContain(".cropduster-form");
    expect(css).not.toMatch(/url\((?!["']?data:)/);
  });

  it("publishes the legacy global and custom element", () => {
    const api = (window as unknown as Record<string, unknown>).CropDuster as
      Record<string, unknown> | undefined;
    expect(api).toBeDefined();
    for (const name of [
      "show",
      "complete",
      "setThumbnails",
      "createThumbnails",
      "registerInput",
      "removeSize",
      "restoreSize",
    ]) {
      expect(typeof api?.[name], name).toBe("function");
    }
    expect(customElements.get("cropduster-widget")).toBeTypeOf("function");
  });

  it("mounts real rows and leaves the empty template alone", () => {
    // lead_image's row has a stored image, so its button offers the crop
    // stage; alt_image is empty and still offers the upload.
    const lead = document.getElementById("lead_image-group")!;
    expect(lead.querySelector(".cropduster-button")?.textContent).toBe(
      "Edit Crops",
    );
    const alt = document.getElementById("alt_image-group")!;
    expect(alt.querySelector(".cropduster-button")?.textContent).toBe(
      "Upload Image",
    );
    const empty = document.getElementById(
      "section_set-empty-items-__prefix__-image-group",
    )!;
    expect(empty.querySelector(".cropduster-images")?.children).toHaveLength(0);
  });
});
