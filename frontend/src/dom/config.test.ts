import { describe, expect, it } from "vitest";

import { DEFAULT_CONFIG, parseConfig, readConfig } from "./config";

describe("parseConfig", () => {
  it("reads the payload the server renders", () => {
    const config = parseConfig(
      JSON.stringify({
        sizes: [{ name: "main", w: 220, h: 180 }],
        uploadTo: "img/uploads/%Y_%m",
        mediaUrl: "/media/",
        fieldIdentifier: "large",
        requireAltText: true,
        preview: {
          url: "/media/p.jpg",
          rendererUrl: "https://thumb.example.com/unsafe/p.jpg",
          srcset:
            "https://thumb.example.com/unsafe/p.jpg, https://thumb.example.com/unsafe/p@2x.jpg 2x",
          w: 800,
          h: 500,
        },
        urls: {
          index: "/cropduster/",
          upload: "/cropduster/upload/",
          crop: "/cropduster/crop/",
          api: "/cropduster/api/v1/",
        },
        dialogMode: "window",
        dispatchInputEvents: false,
        features: { overrideSources: true },
        target: {
          model: "tests.article",
          objectId: 41,
          fieldName: "lead_image",
        },
        labels: { upload: "Choose an image" },
        csrfToken: "abc123",
        debug: true,
      }),
    );

    expect(config).toEqual({
      sizes: [{ name: "main", w: 220, h: 180 }],
      uploadTo: "img/uploads/%Y_%m",
      mediaUrl: "/media/",
      fieldIdentifier: "large",
      requireAltText: true,
      preview: {
        url: "/media/p.jpg",
        rendererUrl: "https://thumb.example.com/unsafe/p.jpg",
        srcset:
          "https://thumb.example.com/unsafe/p.jpg, https://thumb.example.com/unsafe/p@2x.jpg 2x",
        w: 800,
        h: 500,
      },
      urls: {
        index: "/cropduster/",
        upload: "/cropduster/upload/",
        crop: "/cropduster/crop/",
        api: "/cropduster/api/v1/",
      },
      dialogMode: "window",
      dispatchInputEvents: false,
      features: { overrideSources: true },
      target: { model: "tests.article", objectId: 41, fieldName: "lead_image" },
      labels: {
        upload: "Choose an image",
        edit: DEFAULT_CONFIG.labels.edit,
        cropContinue: DEFAULT_CONFIG.labels.cropContinue,
        cropGenerate: DEFAULT_CONFIG.labels.cropGenerate,
        reupload: DEFAULT_CONFIG.labels.reupload,
      },
      csrfToken: "abc123",
      debug: true,
    });
  });

  it("falls back to defaults for a missing, empty or broken attribute", () => {
    for (const raw of [null, undefined, "", "not json", "[]", '"a string"']) {
      const config = parseConfig(raw);
      expect(config.dialogMode).toBe("auto");
      expect(config.dispatchInputEvents).toBe(true);
      expect(config.labels.upload).toBe("Upload Image");
      expect(config.urls.api).toBeNull();
      expect(config.sizes).toBeNull();
    }
  });

  it("ignores values of the wrong type", () => {
    const config = parseConfig(
      JSON.stringify({
        sizes: "nope",
        dialogMode: "sideways",
        dispatchInputEvents: "yes",
        preview: "none",
        urls: 3,
        features: null,
        csrfToken: 7,
      }),
    );

    expect(config.sizes).toBeNull();
    expect(config.dialogMode).toBe("auto");
    expect(config.dispatchInputEvents).toBe(true);
    expect(config.preview).toBeNull();
    expect(config.urls).toEqual(DEFAULT_CONFIG.urls);
    expect(config.features.overrideSources).toBe(false);
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
