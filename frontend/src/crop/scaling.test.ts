import { describe, expect, it } from "vitest";

import { clampCoordinates } from "./geometry";
import { displayScale, toDisplayPx, toSourcePx } from "./scaling";

describe("displayScale", () => {
  it("is Jcrop's trueSize factor", () => {
    // A 3000x2000 original previewed at 800x533.
    expect(displayScale({ w: 3000, h: 2000 }, { w: 800, h: 533 })).toEqual({
      x: 3.75,
      y: 2000 / 533,
    });
  });

  it("is 1 when the canvas shows the source itself", () => {
    expect(displayScale({ w: 674, h: 800 }, { w: 674, h: 800 })).toEqual({
      x: 1,
      y: 1,
    });
  });
});

describe("toSourcePx / toDisplayPx", () => {
  const scale = displayScale({ w: 3000, h: 2000 }, { w: 800, h: 533 });

  it("maps a display box onto the source", () => {
    expect(toSourcePx({ x: 100, y: 50, w: 400, h: 200 }, scale)).toEqual({
      x: 375,
      y: 50 * (2000 / 533),
      w: 1500,
      h: 200 * (2000 / 533),
    });
  });

  it("round trips without rounding", () => {
    const box = { x: 101, y: 51, w: 399, h: 199 };
    expect(toDisplayPx(toSourcePx(box, scale), scale)).toEqual(box);
  });

  it("leaves rounding to clampCoordinates, which rounds once", () => {
    const source = toSourcePx({ x: 10, y: 20, w: 133, h: 67 }, scale);
    expect(Number.isInteger(source.h)).toBe(false);
    const box = clampCoordinates(source);
    expect(box).toEqual({
      x: Math.round(source.x),
      y: Math.round(source.y),
      w: Math.round(source.w),
      h: Math.round(source.h),
    });
    expect(clampCoordinates(box)).toEqual(box);
  });
});
