import { describe, expect, it } from "vitest";

import { dialogConfigJson } from "../testing/dialogFixtures";
import { parseDialogConfig, parseQuery } from "./dialogConfig";

describe("parseQuery", () => {
  it("reads the dialog's own GET parameters", () => {
    expect(
      parseQuery("?el_id=lead_image&sizes=%5B%5D&callback_fn=x_callback"),
    ).toEqual({
      el_id: "lead_image",
      sizes: "[]",
      callback_fn: "x_callback",
    });
  });
});

describe("parseDialogConfig", () => {
  it("reads what the view rendered", () => {
    const rendererUrl = "https://thumb.example.com/unsafe/fit-in/800x500/a.jpg";
    const srcset = `${rendererUrl}, https://thumb.example.com/unsafe/fit-in/1600x1000/a.jpg 2x`;
    const config = parseDialogConfig(
      dialogConfigJson({
        sizes: [{ name: "main", w: 600, h: 480 }],
        elId: "lead_image",
        image: { id: 3, name: "a/original.jpg", width: 1300, height: 1016 },
        crops: { main: { x: 1, y: 2, w: 3, h: 4 } },
        previewRendererUrl: rendererUrl,
        previewSrcset: srcset,
        legacyPreviewBounds: [640, 360],
      }),
    );

    expect(config.elId).toBe("lead_image");
    expect(config.initialState.image).toMatchObject({
      id: 3,
      width: 1300,
      height: 1016,
    });
    expect(config.initialState.thumbs.main).toMatchObject({
      name: "main",
      crop: { x: 1, y: 2, width: 3, height: 4 },
    });
    expect(config.urls.api).toBe("/cropduster/api/v1/");
    expect(config.previewSize).toEqual([800, 500]);
    expect(config.legacyPreviewBounds).toEqual([640, 360]);
    expect(config.initialState.preview?.url).toBe(rendererUrl);
    expect(config.initialState.preview?.srcset).toBe(srcset);
  });

  it("falls back to the query string of a 4.x-era page", () => {
    const config = parseDialogConfig(null, {
      search:
        "?el_id=headshot&callback_fn=cb&upload_to=a%2F%25Y&preview_size=640x480" +
        '&sizes=%5B%7B"name"%3A"main"%7D%5D&cropduster_debug=1',
      pathname: "/cropduster/",
    });

    expect(config.elId).toBe("headshot");
    expect(config.callbackFn).toBe("cb");
    expect(config.uploadTo).toBe("a/%Y");
    expect(config.previewSize).toEqual([640, 480]);
    expect(config.legacyPreviewBounds).toEqual([800, 500]);
    expect(config.initialState.sizes).toEqual([{ name: "main" }]);
    expect(config.initialState.thumbs).toEqual({});
  });

  it("survives a config that is not JSON at all", () => {
    const config = parseDialogConfig("{oops");
    expect(config.initialState.sizes).toEqual([]);
    expect(config.initialState.image).toBeNull();
    expect(config.standalone).toBe(false);
  });
});
