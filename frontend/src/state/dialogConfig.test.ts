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
      }),
    );

    expect(config.elId).toBe("lead_image");
    expect(config.image).toMatchObject({ id: 3, width: 1300, height: 1016 });
    expect(config.thumbs[0]).toMatchObject({
      name: "main",
      crop_x: 1,
      crop_w: 3,
    });
    expect(config.urls.crop).toBe("/cropduster/crop/");
    expect(config.previewSize).toEqual([800, 500]);
    expect(config.preview.rendererUrl).toBe(rendererUrl);
    expect(config.preview.srcset).toBe(srcset);
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
    expect(config.sizes).toEqual([{ name: "main" }]);
    expect(config.debug).toBe(true);
    // Build one crop step per size when only query parameters are available.
    expect(config.thumbs).toHaveLength(1);
    expect(config.thumbs[0]).toMatchObject({ name: "main", crop_x: null });
  });

  it("reads renderer data from the page dialog's crop steps", () => {
    const rendererUrl = "https://thumb.example.com/unsafe/main.jpg";
    const srcset = `${rendererUrl}, https://thumb.example.com/unsafe/main@2x.jpg 2x`;
    const config = parseDialogConfig(
      JSON.stringify({
        sizes: [{ name: "main", w: 600, h: 480 }],
        thumbs: [
          {
            id: 3,
            name: "main",
            width: 600,
            height: 480,
            crop_x: 0,
            crop_y: 0,
            crop_w: 1200,
            crop_h: 960,
            size: { name: "main", w: 600, h: 480 },
            thumbs: {},
            changed: false,
            url: "/media/main.jpg",
            renderer_url: rendererUrl,
            srcset,
          },
        ],
      }),
    );

    expect(config.thumbs[0]).toMatchObject({
      url: "/media/main.jpg",
      rendererUrl,
      srcset,
    });
  });

  it("derives the endpoints from where the dialog is served", () => {
    expect(
      parseDialogConfig(null, { pathname: "/admin/cropduster/standalone/" }),
    ).toMatchObject({
      standalone: true,
      urls: {
        upload: "/admin/cropduster/upload/",
        crop: "/admin/cropduster/crop/",
      },
    });
  });

  it("survives a config that is not JSON at all", () => {
    const config = parseDialogConfig("{oops");
    expect(config.sizes).toEqual([]);
    expect(config.image).toBeNull();
    expect(config.standalone).toBe(false);
  });
});
