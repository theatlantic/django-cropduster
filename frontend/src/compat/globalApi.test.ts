import {
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";
import jQuery from "jquery";

import {
  CropDuster,
  complete,
  installGlobalApi,
  registerInput,
  removeSize,
  restoreSize,
  setThumbnails,
  show,
} from "./globalApi";
import { SIZES_CHANGE_EVENT, UPDATE_EVENT } from "./events";
import { defineWidgetElement } from "../dom/CropDusterWidgetElement";
import { registry } from "../dom/registry";
import type { LegacyCompletePayload } from "../formset/legacyPayload";
import {
  cardQuery,
  cleanupDocument,
  flush,
  mountFixture,
  waitFor,
} from "../testing/fixtures";

const globals = globalThis as unknown as Record<string, unknown>;

beforeAll(() => {
  defineWidgetElement();
});

beforeEach(() => {
  window.history.replaceState({}, "", "/admin/article/1/change/");
});

afterEach(async () => {
  await cleanupDocument();
  delete globals.django;
  delete globals.grp;
  delete globals.jQuery;
  delete globals.$;
  vi.restoreAllMocks();
});

function spyOnOpen() {
  const focus = vi.fn();
  const open = vi
    .spyOn(window, "open")
    .mockReturnValue({ focus } as unknown as Window);
  return { open, focus };
}

describe("show", () => {
  it("builds 4.x's popup URL and window name", () => {
    mountFixture({
      prefix: "lead_image",
      image: "img/uploads/photo.jpg",
      imageId: "5",
      sizes: [{ name: "main", w: 100, h: 50 }],
      thumbs: [
        { id: 11, name: "main" },
        { id: 12, name: "thumb" },
      ],
      withElement: false,
    });
    const { open, focus } = spyOnOpen();

    show("lead_image", "/cropduster/?pop=1");

    expect(open).toHaveBeenCalledWith(
      "/cropduster/?pop=1" +
        "&image=img/uploads/photo.jpg" +
        "&id=5" +
        "&thumbs=11,12" +
        "&sizes=%5B%7B%22name%22:%22main%22,%22w%22:100,%22h%22:50%7D%5D" +
        "&el_id=lead_image",
      "lead_image",
      "height=650,width=960,resizable=yes,scrollbars=yes",
    );
    expect(focus).toHaveBeenCalledTimes(1);
  });

  it("omits empty parameters but always sends sizes", () => {
    mountFixture({ prefix: "lead_image", sizes: [], withElement: false });
    const { open } = spyOnOpen();

    show("lead_image", "/cropduster/?pop=1");

    expect(open.mock.calls[0]?.[0]).toBe(
      "/cropduster/?pop=1&sizes=%5B%5D&el_id=lead_image",
    );
  });

  it("mangles dashes and dots out of the window name", () => {
    mountFixture({
      prefix: "photo_set-3-image",
      sizes: [],
      withElement: false,
    });
    const { open } = spyOnOpen();

    show("photo_set-3-image", "/cropduster/?pop=1");
    show("a.b-c", "/cropduster/?pop=1");

    expect(open.mock.calls[0]?.[1]).toBe("photo_set____3____image");
    expect(open.mock.calls[1]?.[1]).toBe("a___b____c");
  });

  it("passes the debug flag through from the opener's query string", () => {
    window.history.replaceState({}, "", "/admin/?cropduster_debug=1");
    mountFixture({ sizes: [], withElement: false });
    const { open } = spyOnOpen();

    show("lead_image", "/cropduster/?pop=1");

    expect(open.mock.calls[0]?.[0]).toBe(
      "/cropduster/?pop=1&sizes=%5B%5D&el_id=lead_image&cropduster_debug=1",
    );
  });
});

function payload(
  overrides: Partial<LegacyCompletePayload> = {},
): LegacyCompletePayload {
  return {
    crop: {
      image_id: 7,
      orig_image: "img/uploads/photo.jpg",
      orig_w: 1200,
      orig_h: 800,
      thumbs: {
        main: { id: 11, name: "main", width: 220, height: 180, url: "/m.jpg" },
      },
    },
    thumbs: [],
    initial: true,
    preview_url: "/media/preview.jpg",
    preview_w: 800,
    preview_h: 533,
    ...overrides,
  };
}

describe("complete", () => {
  it("writes the formset, the options and the event", async () => {
    const fixture = mountFixture({ withElement: false, initialForms: "0" });
    const seen = vi.fn();
    document.addEventListener(UPDATE_EVENT, seen);

    complete("lead_image", payload());

    expect((fixture.field("id") as HTMLInputElement).value).toBe("7");
    expect(fixture.dataField.value).toBe("img/uploads/photo.jpg");
    expect((fixture.field("TOTAL_FORMS") as HTMLInputElement).value).toBe("1");
    expect((fixture.field("thumbs") as HTMLSelectElement).innerHTML).toBe(
      '<option value="11" data-width="220" data-height="180" data-url="/m.jpg" data-tmp-file="true" selected="selected">main</option>',
    );
    expect(seen).toHaveBeenCalledTimes(1);

    // The widget it adopted renders the preview once it mounts, inside the
    // summary card's shadow root, keeping the 4.x anchor shape.
    await waitFor(() => cardQuery(fixture.images, "a"), {
      message: "the adopted widget to render its preview",
    });
    const anchor = cardQuery<HTMLAnchorElement>(fixture.images, "a")!;
    expect(anchor.className).toBe("cropduster-image cropduster-image-preview");
    expect(anchor.getAttribute("href")).toBe("/media/preview.jpg");
    const img = anchor.querySelector("img")!;
    expect(img.className).toBe(
      "cropduster-image-thumb cropduster-image-thumb-preview",
    );
    expect(img.getAttribute("src")).toBe("/media/preview.jpg");
    expect(img.getAttribute("width")).toBe("800");
    expect(img.getAttribute("height")).toBe("533");
    document.removeEventListener(UPDATE_EVENT, seen);
  });

  it("stops before the thumbnails when the payload has none", () => {
    const fixture = mountFixture({ withElement: false });
    const seen = vi.fn();
    document.addEventListener(UPDATE_EVENT, seen);

    complete(
      "lead_image",
      payload({
        thumbs: undefined as unknown as LegacyCompletePayload["thumbs"],
      }),
    );

    expect((fixture.field("id") as HTMLInputElement).value).toBe("7");
    expect(fixture.field("thumbs")!.querySelectorAll("option")).toHaveLength(0);
    expect(seen).not.toHaveBeenCalled();
    document.removeEventListener(UPDATE_EVENT, seen);
  });

  it("is a no-op for an unknown prefix", () => {
    expect(() => complete("nothing_here", payload())).not.toThrow();
  });
});

describe("setThumbnails", () => {
  it("repopulates the select the way downstream writers do", () => {
    const fixture = mountFixture({
      prefix: "item_set-3-image",
      withElement: false,
      thumbs: [{ id: 1, name: "stale", width: 1, height: 1 }],
    });

    setThumbnails("item_set-3-image", {
      main: { id: 11, name: "main", width: 220, height: 180, url: "/m.jpg" },
    });

    const select = fixture.field("thumbs") as HTMLSelectElement;
    expect([...select.selectedOptions].map((o) => o.value)).toEqual(["11"]);
    expect(select.options[0]?.getAttribute("data-tmp-file")).toBe("true");
  });
});

describe("registerInput", () => {
  it("adopts hand-built markup, once", async () => {
    const fixture = mountFixture({ withElement: false });

    registerInput(fixture.dataField);
    registerInput(fixture.dataField);
    await flush(0);
    registerInput(fixture.dataField);

    expect(fixture.root.querySelectorAll("cropduster-widget")).toHaveLength(1);
    expect(registry.byPrefix("lead_image")).not.toBeNull();
  });

  it("ignores an input outside a widget", () => {
    document.body.innerHTML = '<input class="cropduster-data-field" name="x">';
    expect(() =>
      registerInput(document.querySelector(".cropduster-data-field")),
    ).not.toThrow();
  });
});

describe("removeSize / restoreSize", () => {
  it("splices the array jQuery hands out, in place", () => {
    const fixture = mountFixture({
      sizes: [{ name: "a" }, { name: "b" }, { name: "c" }],
      withElement: false,
    });
    globals.django = { jQuery };
    const shared = jQuery(fixture.dataField).data("sizes") as {
      name: string;
    }[];

    removeSize("lead_image", "b");

    expect(shared.map((s) => s.name)).toEqual(["a", "c"]);
    expect(jQuery(fixture.dataField).data("sizes")).toBe(shared);

    restoreSize("lead_image", "b");

    expect(shared.map((s) => s.name)).toEqual(["a", "b", "c"]);
  });

  it("mutates the array a downstream script swapped in", () => {
    const fixture = mountFixture({
      sizes: [{ name: "a" }],
      withElement: false,
    });
    globals.django = { jQuery };
    const replacement = [{ name: "wide" }, { name: "tall" }];
    jQuery(fixture.dataField).data("sizes", replacement);

    removeSize("lead_image", "wide");

    expect(replacement.map((s) => s.name)).toEqual(["tall"]);
  });

  it("works without jQuery on the page", () => {
    const fixture = mountFixture({
      sizes: [{ name: "a" }, { name: "b" }],
      withElement: false,
    });
    const bridgeSizes = () =>
      JSON.parse(fixture.dataField.getAttribute("data-sizes") ?? "[]") as {
        name: string;
      }[];

    removeSize("lead_image", "a");
    restoreSize("lead_image", "a");

    // The attribute is never rewritten; the live array is the channel.
    expect(bridgeSizes().map((s) => s.name)).toEqual(["a", "b"]);
    expect(registry.byPrefix("lead_image")).toBeNull();
  });

  it("dispatches the change on the 6.0 channel", () => {
    mountFixture({ sizes: [{ name: "a" }], withElement: false });
    const seen = vi.fn();
    document.addEventListener(SIZES_CHANGE_EVENT, seen);

    removeSize("lead_image", "a");
    restoreSize("lead_image", "a");

    expect(seen).toHaveBeenCalledTimes(2);
    expect((seen.mock.calls[0]?.[0] as CustomEvent).detail).toEqual({
      prefix: "lead_image",
    });
    document.removeEventListener(SIZES_CHANGE_EVENT, seen);
  });

  it("ignores unknown sizes and unremoved restores", () => {
    const fixture = mountFixture({
      sizes: [{ name: "a" }],
      withElement: false,
    });

    removeSize("lead_image", "nope");
    restoreSize("lead_image", "a");
    removeSize("missing_prefix", "a");

    expect(
      JSON.parse(fixture.dataField.getAttribute("data-sizes") ?? "[]"),
    ).toEqual([{ name: "a" }]);
  });
});

describe("installGlobalApi", () => {
  it("publishes the 4.x surface on window", () => {
    installGlobalApi();
    expect(window.CropDuster).toBe(CropDuster);
    for (const method of [
      "show",
      "complete",
      "setThumbnails",
      "createThumbnails",
      "registerInput",
      "removeSize",
      "restoreSize",
    ]) {
      expect(
        typeof (window.CropDuster as unknown as Record<string, unknown>)[
          method
        ],
      ).toBe("function");
    }
    expect(typeof window.CropDuster?.mediaUrl).toBe("string");
  });

  it("picks up the media URL of the last widget mounted", async () => {
    mountFixture({ prefix: "lead_image", mediaUrl: "/media/" });
    await flush(0);
    expect(CropDuster.mediaUrl).toBe("/media/");
  });
});
