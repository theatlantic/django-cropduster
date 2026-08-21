import { describe, expect, it } from "vitest";

import type { DialogMode } from "../dom/config";
import { fitsModal, pickPresentation } from "./pickPresentation";

/** Minimal Window object used by the viewport checks. */
function view(width: number, height: number): Window {
  return { innerWidth: width, innerHeight: height } as unknown as Window;
}

describe("pickPresentation", () => {
  const cases: [DialogMode, number, number, string][] = [
    // Explicit settings do not depend on viewport size.
    ["modal", 320, 200, "modal"],
    ["window", 1920, 1080, "window"],
    // `auto` uses 900x600 as the modal cutoff.
    ["auto", 1280, 800, "modal"],
    ["auto", 900, 600, "modal"],
    ["auto", 899, 600, "window"],
    ["auto", 900, 599, "window"],
    // A downstream editor embed: an 830x550 `scrolling="no"` iframe.
    ["auto", 830, 550, "window"],
  ];

  for (const [dialogMode, width, height, expected] of cases) {
    it(`picks ${expected} for ${dialogMode} at ${width}x${height}`, () => {
      expect(pickPresentation({ dialogMode }, view(width, height))).toBe(
        expected,
      );
    });
  }

  // Framing is irrelevant; selection uses the frame's own viewport.
  it("measures a frame the way it measures any other viewport", () => {
    expect(pickPresentation({ dialogMode: "auto" }, view(830, 550))).toBe(
      "window",
    );
    expect(pickPresentation({ dialogMode: "auto" }, view(1200, 800))).toBe(
      "modal",
    );
  });

  it("reads the viewport it is handed, defaulting to this one", () => {
    expect(fitsModal(view(960, 650))).toBe(true);
    expect(fitsModal(view(960, 400))).toBe(false);
    expect(pickPresentation({ dialogMode: "window" })).toBe("window");
  });
});
