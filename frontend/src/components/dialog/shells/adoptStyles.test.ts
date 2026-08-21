/**
 * The `:root` → `:host` rewrite is what keeps library custom properties alive
 * inside the shadow tree. jsdom cannot resolve `var()` through its cascade,
 * so these tests pin the transform and the adopted text rather than computed
 * styles; e2e/resize.spec.ts proves the rendered result in a real browser.
 */

import { readFileSync } from "node:fs";
import { createRequire } from "node:module";

import { afterEach, describe, expect, it } from "vitest";

import {
  adoptDialogStyles,
  adoptStyles,
  hostifyRootSelectors,
  refreshDialogStyles,
  releaseDialogStyles,
} from "./adoptStyles";

// Read the real shipped stylesheet: vitest resolves `?inline` imports to
// empty strings, which would make an assertion through DIALOG_STYLES vacuous.
const require = createRequire(import.meta.url);
const reactCropCss = readFileSync(
  require.resolve("react-image-crop/dist/ReactCrop.css"),
  "utf8",
);

function adoptedText(root: ShadowRoot): string {
  const texts =
    root.adoptedStyleSheets && root.adoptedStyleSheets.length
      ? root.adoptedStyleSheets.map((sheet) =>
          [...sheet.cssRules].map((rule) => rule.cssText).join(""),
        )
      : [...root.querySelectorAll("style")].map((el) => el.textContent);
  return texts.join("\n");
}

afterEach(() => {
  // Vitest resolves the three `?inline` imports to empty strings.
  refreshDialogStyles({ reactCrop: "", dialog: "", modal: "" });
  document.body.replaceChildren();
});

describe("hostifyRootSelectors", () => {
  it("rewrites a minified :root block", () => {
    expect(hostifyRootSelectors(":root{--a:1px}")).toBe(":host{--a:1px}");
  });

  it("rewrites :root wherever it appears as a selector", () => {
    expect(
      hostifyRootSelectors("@keyframes x{0%{}}:root{--a:1px}\n:root ,p{}"),
    ).toBe("@keyframes x{0%{}}:host{--a:1px}\n:host ,p{}");
  });

  it("leaves non-selector occurrences alone", () => {
    const css = '.a{background:url("x:rooty.png")}.b:rooted{}';
    expect(hostifyRootSelectors(css)).toBe(css);
  });

  it("react-image-crop's handle variables survive adoption", () => {
    expect(reactCropCss).toContain(":root{--rc-drag-handle-size:12px");
    const adopted = hostifyRootSelectors(reactCropCss);
    expect(adopted).toContain(":host{--rc-drag-handle-size:12px");
    expect(adopted).not.toMatch(/(^|[\s,{}]):root(?![\w-])/);
  });
});

describe("adoptStyles", () => {
  it("adopts the hostified text into the shadow root", () => {
    const host = document.createElement("div");
    document.body.appendChild(host);
    const root = host.attachShadow({ mode: "open" });
    adoptStyles(root, [":root{--probe:7px}"]);
    const all = adoptedText(root);
    expect(all).toContain(":host");
    expect(all).not.toContain(":root");
  });

  it("replaces its existing sheets instead of appending duplicates", () => {
    const host = document.createElement("div");
    document.body.appendChild(host);
    const root = host.attachShadow({ mode: "open" });
    adoptStyles(root, [":host{--probe:1px}"]);
    const firstSheets = Array.from(root.adoptedStyleSheets ?? []);
    const firstElements = [...root.querySelectorAll("style")];

    adoptStyles(root, [":host{--probe:2px}"]);

    expect(adoptedText(root)).toMatch(/--probe:\s*2px/);
    expect(adoptedText(root)).not.toMatch(/--probe:\s*1px/);
    if (firstSheets.length) {
      expect(root.adoptedStyleSheets).toEqual(firstSheets);
    } else {
      expect([...root.querySelectorAll("style")]).toEqual(firstElements);
    }
  });
});

describe("dialog style refresh", () => {
  it("updates page and modal roots in place with the right cascade", () => {
    const pageHost = document.createElement("div");
    const modalHost = document.createElement("cropduster-dialog");
    document.body.append(pageHost, modalHost);
    const page = pageHost.attachShadow({ mode: "open" });
    const modal = modalHost.attachShadow({ mode: "open" });
    adoptDialogStyles(page, "page");
    adoptDialogStyles(modal, "modal");

    refreshDialogStyles({
      dialog: ":root{--dialog-hot:1px}",
      modal: ":host{--modal-hot:2px}",
    });

    expect(adoptedText(page)).toMatch(/--dialog-hot:\s*1px/);
    expect(adoptedText(page)).not.toContain("--modal-hot");
    expect(adoptedText(modal)).toMatch(/--dialog-hot:\s*1px/);
    expect(adoptedText(modal)).toMatch(/--modal-hot:\s*2px/);
    releaseDialogStyles(page);
    releaseDialogStyles(modal);
  });

  it("stops retaining a root once its host disconnects", () => {
    const host = document.createElement("cropduster-dialog");
    document.body.appendChild(host);
    const root = host.attachShadow({ mode: "open" });
    adoptDialogStyles(root, "modal");
    host.remove();

    refreshDialogStyles({ dialog: ":host{--while-detached:1px}" });
    document.body.appendChild(host);
    refreshDialogStyles({ dialog: ":host{--after-reconnect:2px}" });

    expect(adoptedText(root)).not.toContain("--while-detached");
    expect(adoptedText(root)).not.toContain("--after-reconnect");
  });
});
