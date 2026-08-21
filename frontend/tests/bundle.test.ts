/**
 * Evaluate the committed production bundle in jsdom.
 *
 * This verifies the file Django serves, both mount paths, and the absence of
 * dynamic imports or unresolved CSS asset URLs.
 */

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

/** What `cropduster/upload.html` renders into `#cropduster-app`. */
const DIALOG_CONFIG = JSON.stringify({
  elId: "lead_image",
  standalone: false,
  sizes: [{ __type__: "Size", name: "main", w: 220, h: 180 }],
  image: null,
  thumbs: [],
  cropThumbs: {},
  preview: { url: "/static/cropduster/img/blank.gif", w: 800, h: 500 },
  urls: { upload: "/cropduster/upload/", crop: "/cropduster/crop/" },
});

/** What the compat layer publishes, and what downstream calls. */
const LEGACY_API = [
  "show",
  "complete",
  "setThumbnails",
  "createThumbnails",
  "registerInput",
  "removeSize",
  "restoreSize",
];

interface LegacyGlobal {
  mediaUrl: string;
  complete(prefix: string, data: unknown, rendererMedia?: unknown): void;
}

function legacyGlobal(): LegacyGlobal {
  const api = (window as unknown as Record<string, unknown>).CropDuster;
  if (!api) {
    throw new Error("the bundle did not install window.CropDuster");
  }
  return api as LegacyGlobal;
}

/** The preview image inside the summary card's shadow root. */
function cardThumb(prefix: string): Element | null {
  return (
    document
      .getElementById(`${prefix}-group`)!
      .querySelector(".cropduster-images")
      ?.shadowRoot?.querySelector(".cropduster-image-thumb") ?? null
  );
}

beforeAll(async () => {
  // A change form with two widgets on it, plus a nested inline's empty-form
  // template, all present before the bundle runs, as on a real page load.
  document.body.innerHTML =
    fixtureHtml("article_change_lead_and_alt") +
    fixtureHtml("nested_empty_item") +
    // The dialog page's mount point, so that both surfaces the bundle serves
    // boot from the one evaluation.
    `<div id="cropduster-app" data-config='${DIALOG_CONFIG}'></div>`;

  // Evaluated once for the whole file: a second evaluation would build a
  // second registry, and the elements would stay upgraded with the first.
  (0, eval)(read("cropduster.js"));
  document.dispatchEvent(new Event("DOMContentLoaded"));
  await waitFor(
    () =>
      ["lead_image", "alt_image"].every((prefix) =>
        isWidgetMounted(document.getElementById(`${prefix}-group`)!),
      ) &&
      Boolean(cardThumb("lead_image")) &&
      Boolean(
        document
          .getElementById("cropduster-app")
          ?.shadowRoot?.getElementById("id_image"),
      ),
    { message: "the bundle to mount both widgets and the dialog" },
  );
});

// Teardown is deferred by a timer so that a widget mid-drag survives being
// detached; the environment must outlive it.
afterAll(cleanupDocument);

describe("the built bundle", () => {
  it("ships a stylesheet Django's Media can own", () => {
    const css = read("cropduster.css");
    expect(css).toContain(".cropduster-form");
    // Inlined as data URIs, so collectstatic has nothing to resolve.
    expect(css).not.toMatch(/url\((?!["']?data:)/);
  });

  it("is one file, with nothing for collectstatic to chase", () => {
    const js = read("cropduster.js");
    expect(js).not.toMatch(/\bimport\s*\(/);
    expect(js).not.toContain("import.meta");
    expect(js).toContain("//# sourceMappingURL=cropduster.js.map");
  });

  it("installs window.CropDuster before anything asks for it", () => {
    const api = legacyGlobal() as unknown as Record<string, unknown>;
    for (const method of LEGACY_API) {
      expect(typeof api[method], method).toBe("function");
    }
    expect(typeof api.mediaUrl).toBe("string");
    // Read from `.cropduster-form[data-media-url]`, as 4.x did.
    expect(api.mediaUrl).toBe("/media/");
  });

  it("registers the custom element", () => {
    expect(customElements.get("cropduster-widget")).toBeTypeOf("function");
  });

  it("mounts the widgets that were on the page", () => {
    // lead_image has a stored image, so its button offers the crop dialog;
    // alt_image is empty and still offers the upload.
    for (const [prefix, label] of [
      ["lead_image", "Edit Crops"],
      ["alt_image", "Upload Image"],
    ]) {
      const root = document.getElementById(`${prefix}-group`)!;
      const button = root.querySelector(
        ".cropduster-customfield .cropduster-button",
      );
      expect(button, prefix).not.toBeNull();
      expect(button?.textContent, prefix).toBe(label);
    }
    // The saved image renders its preview into the shadow root the widget
    // attaches to the server-rendered container.
    const preview = cardThumb("lead_image");
    expect(preview?.getAttribute("src")).toBe(
      "/media/article/lead_image/{Y}/{m}/img/_preview.jpg?mod={MOD}",
    );
    expect(preview?.hasAttribute("srcset")).toBe(false);
  });

  it("leaves the empty-form template alone", () => {
    const root = document.getElementById(
      "section_set-empty-items-__prefix__-image-group",
    )!;
    const images = root.querySelector(".cropduster-images")!;
    expect(images.children).toHaveLength(0);
    // Mounting would have attached the card's shadow root.
    expect(images.shadowRoot).toBeNull();
  });

  it("mounts the dialog into a shadow root of its own", () => {
    const host = document.getElementById("cropduster-app")!;
    const shadow = host.shadowRoot!;

    expect(shadow).not.toBeNull();
    expect(host.children).toHaveLength(0);
    // The dialog's stylesheet is embedded in the bundle rather than in the
    // file Django's Media links, because a link cannot reach into a shadow
    // root.
    expect(read("cropduster.css")).not.toContain("cropduster-dialog");
    expect(shadow.textContent).toContain("Min. size:");

    for (const id of ["id_image", "cropbox", "upload-button"]) {
      expect([id, shadow.getElementById(id) !== null]).toEqual([id, true]);
    }
    expect(shadow.getElementById("step-header")).toBeNull();
    expect(shadow.getElementById("primary-image-help")).toBeNull();
    expect(shadow.querySelector(".upload-stage-copy")).toBeNull();
    expect(shadow.getElementById("crop-button")).toBeNull();
    expect(shadow.querySelector(".upload-file-title")?.textContent).toBe(
      "Upload an image",
    );
    expect(shadow.getElementById("upload-footer")?.hidden).toBe(true);
    expect(shadow.getElementById("upload-button")?.parentElement?.hidden).toBe(
      true,
    );

    const dialog = (window as unknown as Record<string, unknown>)
      .CropDusterDialog as { canCommit(): boolean } | undefined;
    expect(dialog?.canCommit()).toBe(false);
  });

  it("mounts a widget inserted after boot", async () => {
    const row = document.createElement("div");
    row.innerHTML = fixtureHtml("author_add_headshot");
    document.body.appendChild(row);
    await waitFor(() => isWidgetMounted(row), {
      message: "the inserted row to mount",
    });

    const button = row.querySelector(
      ".cropduster-customfield .cropduster-button",
    );
    expect(button).not.toBeNull();
    expect(button?.textContent).toBe("Upload Image");
  });
});
