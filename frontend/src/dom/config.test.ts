import { describe, expect, it } from "vitest";

import { DEFAULT_CONFIG, parseConfig, readConfig } from "./config";

describe("parseConfig", () => {
  it("reads the payload the server renders", () => {
    const config = parseConfig(
      JSON.stringify({
        uploadTo: "img/uploads/%Y_%m",
        mediaUrl: "/media/",
        legacyPreviewBounds: { w: 640, h: 360 },
        urls: {
          api: "/cropduster/api/v1/",
        },
        dialogMode: "window",
        dispatchInputEvents: false,
        target: {
          model: "tests.article",
          objectId: 41,
          fieldName: "lead_image",
        },
        labels: { upload: "Choose an image" },
        csrfToken: "abc123",
      }),
    );

    expect(config).toEqual({
      uploadTo: "img/uploads/%Y_%m",
      mediaUrl: "/media/",
      legacyPreviewBounds: [640, 360],
      urls: {
        api: "/cropduster/api/v1/",
      },
      dialogMode: "window",
      dispatchInputEvents: false,
      target: { model: "tests.article", objectId: 41, fieldName: "lead_image" },
      labels: {
        upload: "Choose an image",
        edit: DEFAULT_CONFIG.labels.edit,
      },
      csrfToken: "abc123",
    });
  });

  it("falls back to defaults for a missing, empty or broken attribute", () => {
    for (const raw of [null, undefined, "", "not json", "[]", '"a string"']) {
      const config = parseConfig(raw);
      expect(config.dialogMode).toBe("auto");
      expect(config.dispatchInputEvents).toBe(true);
      expect(config.labels.upload).toBe("Upload Image");
      expect(config.urls.api).toBeNull();
      expect(config.legacyPreviewBounds).toEqual([800, 500]);
    }
  });

  it("ignores values of the wrong type", () => {
    const config = parseConfig(
      JSON.stringify({
        dialogMode: "sideways",
        dispatchInputEvents: "yes",
        urls: 3,
        legacyPreviewBounds: "large",
        csrfToken: 7,
      }),
    );

    expect(config.dialogMode).toBe("auto");
    expect(config.dispatchInputEvents).toBe(true);
    expect(config.urls).toEqual(DEFAULT_CONFIG.urls);
    expect(config.legacyPreviewBounds).toEqual([800, 500]);
    expect(config.csrfToken).toBeNull();
  });

  it("takes a target only when it names both a model and a field", () => {
    const target = (value: unknown) =>
      parseConfig(JSON.stringify({ target: value })).target;

    // An add form: no object yet, which the API reads as "no instance".
    expect(
      target({ model: "tests.article", objectId: null, fieldName: "headshot" }),
    ).toEqual({
      model: "tests.article",
      objectId: null,
      fieldName: "headshot",
    });
    // A non-integer pk survives as it was written.
    expect(
      target({ model: "a.b", objectId: "7f-uuid", fieldName: "c" }),
    ).toEqual({ model: "a.b", objectId: "7f-uuid", fieldName: "c" });
    for (const broken of [
      undefined,
      null,
      "tests.article",
      {},
      { model: "tests.article" },
      { fieldName: "headshot" },
      { model: "", objectId: 1, fieldName: "headshot" },
    ]) {
      expect(target(broken)).toBeNull();
    }
  });

  it("does not hand out the shared default objects", () => {
    const first = parseConfig(null);
    const second = parseConfig(null);
    expect(first.urls).not.toBe(second.urls);
    expect(first.urls).not.toBe(DEFAULT_CONFIG.urls);
    expect(first.legacyPreviewBounds).not.toBe(second.legacyPreviewBounds);
    expect(first.legacyPreviewBounds).not.toBe(
      DEFAULT_CONFIG.legacyPreviewBounds,
    );
  });
});

describe("readConfig", () => {
  it("reads data-config off the element", () => {
    const el = document.createElement("cropduster-widget");
    el.setAttribute("data-config", '{"mediaUrl":"/uploads/"}');
    expect(readConfig(el).mediaUrl).toBe("/uploads/");
  });

  it("tolerates an element with no config at all", () => {
    expect(readConfig(document.createElement("div")).mediaUrl).toBe("");
  });
});
