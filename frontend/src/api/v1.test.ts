import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { dialogConfig } from "../testing/dialogFixtures";
import { headshotUpload, HEADSHOT_SIZES } from "../testing/canonicalFixtures";
import type { DialogConfig } from "../state/dialogConfig";
import {
  API_UNAVAILABLE,
  crop,
  csrfToken,
  DialogError,
  getState,
  isSourceUnsupported,
  PER_SIZE_SOURCE_UNSUPPORTED,
  UNKNOWN_ERROR,
  upload,
} from "./v1";

function config(overrides: Partial<DialogConfig> = {}): DialogConfig {
  return { ...dialogConfig({ sizes: HEADSHOT_SIZES }), ...overrides };
}

function stub(body: unknown, init: { status?: number } = {}) {
  const status = init.status ?? 200;
  const fetchMock = vi.fn<
    (url: string, init?: RequestInit) => Promise<Response>
  >(() =>
    Promise.resolve({
      ok: status < 400,
      status,
      json: () => Promise.resolve(body),
    } as Response),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function lastInit(fetchMock: ReturnType<typeof stub>): RequestInit {
  return fetchMock.mock.calls[0]?.[1] as unknown as RequestInit;
}

function header(fetchMock: ReturnType<typeof stub>, name: string) {
  return (lastInit(fetchMock).headers as Record<string, string>)[name];
}

beforeEach(() => {
  document.cookie = "csrftoken=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
  document.body.innerHTML = "";
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("csrfToken", () => {
  it("prefers the token the widget was rendered with", () => {
    document.cookie = "csrftoken=from-cookie";
    expect(csrfToken({ csrfToken: "from-config" })).toBe("from-config");
  });

  it("falls back to the cookie, then to the page's hidden input", () => {
    document.cookie = "csrftoken=from-cookie";
    expect(csrfToken({ csrfToken: null })).toBe("from-cookie");

    document.cookie = "csrftoken=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
    document.body.innerHTML =
      '<input type="hidden" name="csrfmiddlewaretoken" value="from-input">';
    expect(csrfToken({ csrfToken: null })).toBe("from-input");
  });

  it("answers nothing when the page has no token at all", () => {
    expect(csrfToken({ csrfToken: null })).toBeNull();
  });

  it("reads its own cookie out of a jar full of others", () => {
    document.cookie = "sessionid=abc";
    document.cookie = "csrftoken=mine";
    document.cookie = "other=csrftoken";
    expect(csrfToken({ csrfToken: null })).toBe("mine");
  });
});

describe("requests", () => {
  it("asks the versioned API, with the token and the session cookie", async () => {
    const fetchMock = stub(headshotUpload());
    const payload = await crop(config({ csrfToken: "tok" }), { sizes: [] });

    expect(fetchMock.mock.calls[0]?.[0]).toBe("/cropduster/api/v1/crop/");
    expect(lastInit(fetchMock).method).toBe("POST");
    expect(lastInit(fetchMock).credentials).toBe("same-origin");
    expect(header(fetchMock, "X-CSRFToken")).toBe("tok");
    expect(header(fetchMock, "Content-Type")).toBe("application/json");
    expect(JSON.parse(String(lastInit(fetchMock).body))).toEqual({ sizes: [] });
    expect(payload.version).toBe(1);
  });

  it("sends no token header when there is no token to send", async () => {
    const fetchMock = stub(headshotUpload());
    await crop(config({ csrfToken: null }), {});

    expect(header(fetchMock, "X-CSRFToken")).toBeUndefined();
  });

  it("posts the state request with its parameters", async () => {
    const fetchMock = stub(headshotUpload());
    await getState(config(), {
      image: "img/original.jpg",
      id: "3",
      thumbs: "1,2",
      upload_to: "",
    });

    expect(fetchMock.mock.calls[0]?.[0]).toBe("/cropduster/api/v1/state/");
    expect(lastInit(fetchMock).method).toBe("POST");
    const body = lastInit(fetchMock).body as URLSearchParams;
    expect(body.get("image")).toBe("img/original.jpg");
    expect(body.get("id")).toBe("3");
    expect(body.get("thumbs")).toBe("1,2");
    // Omit an empty value instead of asking the endpoint to interpret it.
    expect(body.has("upload_to")).toBe(false);
  });

  /**
   * Include the field target with every request so `parse_target()` can load
   * the field's declared sizes and `upload_to`.
   */
  describe("the target the widget was rendered with", () => {
    const targeted = () =>
      config({
        target: {
          model: "tests.article",
          objectId: 41,
          fieldName: "lead_image",
        },
      });
    const WIRE = {
      content_type: "tests.article",
      object_id: 41,
      field_name: "lead_image",
    };

    it("rides along on state, upload and crop", async () => {
      const state = stub(headshotUpload());
      await getState(targeted(), { image: "img/original.jpg" });
      const stateBody = lastInit(state).body as URLSearchParams;
      expect(JSON.parse(stateBody.get("target") ?? "null")).toEqual(WIRE);

      vi.unstubAllGlobals();
      const uploaded = stub(headshotUpload());
      await upload(targeted(), new FormData());
      expect(
        JSON.parse(String((lastInit(uploaded).body as FormData).get("target"))),
      ).toEqual(WIRE);

      vi.unstubAllGlobals();
      const cropped = stub(headshotUpload());
      await crop(targeted(), { sizes: [], thumbs: {} });
      expect(JSON.parse(String(lastInit(cropped).body))).toEqual({
        sizes: [],
        thumbs: {},
        target: WIRE,
      });
    });

    it("names no target when the dialog was not opened on a field", async () => {
      const state = stub(headshotUpload());
      await getState(config(), { image: "img/original.jpg" });
      expect((lastInit(state).body as URLSearchParams).has("target")).toBe(
        false,
      );

      vi.unstubAllGlobals();
      const cropped = stub(headshotUpload());
      await crop(config(), { sizes: [] });
      expect(JSON.parse(String(lastInit(cropped).body))).toEqual({ sizes: [] });
    });

    it("sends a null object_id for an object that is not saved yet", async () => {
      const fetchMock = stub(headshotUpload());
      await upload(
        config({
          target: {
            model: "tests.author",
            objectId: null,
            fieldName: "headshot",
          },
        }),
        new FormData(),
      );

      expect(
        JSON.parse(
          String((lastInit(fetchMock).body as FormData).get("target")),
        ),
      ).toEqual({
        content_type: "tests.author",
        object_id: null,
        field_name: "headshot",
      });
    });
  });

  it("passes for_size through, which scopes the upload's minimums", async () => {
    const fetchMock = stub(headshotUpload());
    const body = new FormData();
    body.append("image", new File(["x"], "img.jpg"));
    await upload(config(), body, { forSize: "main" });

    expect(fetchMock.mock.calls[0]?.[0]).toBe("/cropduster/api/v1/upload/");
    expect((lastInit(fetchMock).body as FormData).get("for_size")).toBe("main");
    // The browser supplies the multipart boundary and Content-Type.
    expect(header(fetchMock, "Content-Type")).toBeUndefined();
  });
});

describe("failures", () => {
  it("reports the error envelope, field and details", async () => {
    stub(
      {
        error: {
          code: "image_too_small",
          message: "The image is 255x80; it has to be at least 220x180.",
          field: "image",
          details: { min: [220, 180], actual: [255, 80] },
        },
      },
      { status: 400 },
    );

    const error = await upload(config(), new FormData()).catch(
      (e: unknown) => e,
    );

    expect(error).toBeInstanceOf(DialogError);
    expect(error).toMatchObject({
      status: 400,
      code: "image_too_small",
      field: "image",
      message: "The image is 255x80; it has to be at least 220x180.",
      details: { min: [220, 180], actual: [255, 80] },
    });
  });

  it("tells the reserved wire apart from a bug", async () => {
    stub(
      {
        error: {
          code: PER_SIZE_SOURCE_UNSUPPORTED,
          message:
            "Cropping 'main' from a source other than the image being cropped is not implemented.",
          field: "thumbs.main",
          details: { source: "other/original.jpg" },
        },
      },
      { status: 501 },
    );

    const error = await crop(config(), {}).catch((e: unknown) => e);

    expect(isSourceUnsupported(error)).toBe(true);
    expect((error as DialogError).status).toBe(501);
    expect(isSourceUnsupported(new DialogError("boom", { status: 500 }))).toBe(
      false,
    );
  });

  it("answers a failure that included no envelope with a usable message", async () => {
    stub("<html>502 Bad Gateway</html>", { status: 502 });

    const error = (await crop(config(), {}).catch(
      (e: unknown) => e,
    )) as DialogError;

    expect(error.message).toBe(UNKNOWN_ERROR);
    expect(error.code).toBe("server_error");
    expect(error.status).toBe(502);
  });

  it("answers a request that never reached the server", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.reject(new TypeError("network"))),
    );

    const error = (await crop(config(), {}).catch(
      (e: unknown) => e,
    )) as DialogError;

    expect(error.code).toBe("network_error");
    expect(error.message).toBe(UNKNOWN_ERROR);
  });

  it("says so when the project routed 4.x's views without the API", async () => {
    const routed = config();
    routed.urls = { ...routed.urls, api: null };

    const error = (await crop(routed, {}).catch(
      (e: unknown) => e,
    )) as DialogError;

    expect(error.code).toBe(API_UNAVAILABLE);
  });
});
