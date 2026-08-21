import { describe, expect, it } from "vitest";

import { edgeResizeCrop, isEdgeOrd } from "./edgeResize";
import type { EdgeResizeParams } from "./edgeResize";

/** 600x480's ratio inside an 800x500 preview. */
const BASE: Omit<EdgeResizeParams, "ord" | "primary" | "anchor" | "center"> = {
  aspect: 1.25,
  bounds: { w: 800, h: 500 },
};

describe("isEdgeOrd", () => {
  it("accepts exactly the four edges", () => {
    expect(["n", "e", "s", "w"].every(isEdgeOrd)).toBe(true);
    expect(["ne", "nw", "se", "sw", undefined, ""].some(isEdgeOrd)).toBe(false);
  });
});

describe("edgeResizeCrop", () => {
  it("keeps the west edge and midline while dragging east", () => {
    const out = edgeResizeCrop({
      ...BASE,
      ord: "e",
      anchor: 100,
      center: 250,
      primary: 400,
    });
    expect(out).toEqual({ unit: "px", x: 100, y: 90, width: 400, height: 320 });
  });

  it("keeps the east edge while dragging west", () => {
    const out = edgeResizeCrop({
      ...BASE,
      ord: "w",
      anchor: 700,
      center: 250,
      primary: 300,
    });
    expect(out.x + out.width).toBe(700);
    expect(out.y).toBe(130);
    expect(out.height).toBe(240);
  });

  it("keeps the south edge while dragging north", () => {
    const out = edgeResizeCrop({
      ...BASE,
      ord: "n",
      anchor: 450,
      center: 400,
      primary: 200,
    });
    expect(out.y + out.height).toBe(450);
    expect(out.width).toBe(250);
    expect(out.x).toBe(275);
  });

  it("keeps the north edge while dragging south", () => {
    const out = edgeResizeCrop({
      ...BASE,
      ord: "s",
      anchor: 50,
      center: 400,
      primary: 360,
    });
    expect(out.y).toBe(50);
    expect(out.height).toBe(360);
    expect(out.width).toBe(450);
    expect(out.x).toBe(175);
  });

  it("slides along the perpendicular axis when centering runs out of room", () => {
    const high = edgeResizeCrop({
      ...BASE,
      ord: "e",
      anchor: 100,
      center: 100,
      primary: 400,
    });
    expect(high.y).toBe(0);

    const low = edgeResizeCrop({
      ...BASE,
      ord: "e",
      anchor: 100,
      center: 450,
      primary: 400,
    });
    expect(low.y).toBe(180);
  });

  it("caps the demand by the anchor's room and the perpendicular fit", () => {
    const out = edgeResizeCrop({
      ...BASE,
      ord: "e",
      anchor: 100,
      center: 250,
      primary: 900,
    });
    // min(800 - 100, 500 * 1.25, 800) = 625, the full-height crop.
    expect(out.width).toBe(625);
    expect(out.height).toBe(500);
    expect(out.y).toBe(0);
  });

  it("bottoms out at the effective minimum instead of flipping", () => {
    const out = edgeResizeCrop({
      ...BASE,
      ord: "e",
      anchor: 100,
      center: 250,
      primary: -80,
      minWidth: 240,
      minHeight: 240,
    });
    // min height 240 implies width 300, which beats min width 240.
    expect(out.width).toBe(300);
    expect(out.height).toBe(240);
    expect(out.x).toBe(100);
  });

  it("prefers fitting over an impossible minimum", () => {
    const out = edgeResizeCrop({
      ...BASE,
      ord: "e",
      anchor: 700,
      center: 250,
      primary: 50,
      minWidth: 400,
    });
    expect(out.width).toBe(100);
    expect(out.x).toBe(700);
  });

  it("respects explicit maximums", () => {
    const out = edgeResizeCrop({
      ...BASE,
      ord: "e",
      anchor: 0,
      center: 250,
      primary: 700,
      maxWidth: 500,
      maxHeight: 300,
    });
    // maxHeight 300 implies width 375, tighter than maxWidth 500.
    expect(out.width).toBe(375);
    expect(out.height).toBe(300);
  });
});
