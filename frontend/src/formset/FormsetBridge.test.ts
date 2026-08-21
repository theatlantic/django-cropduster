import { afterEach, describe, expect, it, vi } from "vitest";

import { FormsetBridge } from "./FormsetBridge";
import type { LegacyCompletePayload } from "./legacyPayload";
import { cleanupDocument, flush, mountFixture } from "../testing/fixtures";

afterEach(cleanupDocument);

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
        thumb: { id: 12, name: "thumb", width: 90, height: 60, url: "/t.jpg" },
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

describe("prefix and lookups", () => {
  it("re-derives the prefix after a rename", () => {
    const fixture = mountFixture({
      prefix: "photo_set-0-image",
      withElement: false,
    });
    const bridge = new FormsetBridge(fixture.root);
    expect(bridge.prefix).toBe("photo_set-0-image");

    // What nested-admin's _fillGap does when an earlier row is deleted.
    for (const el of fixture.root.querySelectorAll("[name],[id]")) {
      for (const attribute of ["name", "id"]) {
        const value = el.getAttribute(attribute);
        if (value) {
          el.setAttribute(
            attribute,
            value.replace("photo_set-0", "photo_set-1"),
          );
        }
      }
    }

    expect(bridge.prefix).toBe("photo_set-1-image");
    expect(bridge.field("image")?.getAttribute("name")).toBe(
      "photo_set-1-image-0-image",
    );
    bridge.destroy();
  });

  it("scopes lookups to its own root", () => {
    const first = mountFixture({ prefix: "lead_image", withElement: false });
    mountFixture({ prefix: "lead_image", withElement: false });
    const bridge = new FormsetBridge(first.root);

    expect(first.root.contains(bridge.field("image"))).toBe(true);
    expect(first.root.contains(bridge.mgmt("TOTAL_FORMS"))).toBe(true);
    bridge.destroy();
  });

  it("reads the live sizes array", () => {
    const fixture = mountFixture({
      sizes: [{ name: "main" }, { name: "thumb" }],
      withElement: false,
    });
    const bridge = new FormsetBridge(fixture.root);
    expect(bridge.readSizes().map((s) => s.name)).toEqual(["main", "thumb"]);
    bridge.destroy();
  });
});

describe("readState", () => {
  it("reads the formset, the selected thumbs and the preview", () => {
    const fixture = mountFixture({
      image: "img/uploads/photo.jpg",
      imageId: "7",
      withElement: false,
      thumbs: [
        { id: 11, name: "main", width: 220, height: 180, url: "/m.jpg" },
        {
          id: 12,
          name: "thumb",
          width: 90,
          height: 60,
          url: "/t.jpg",
          selected: false,
          tmp: false,
        },
      ],
    });
    const bridge = new FormsetBridge(fixture.root);
    const state = bridge.readState();

    expect(state).toMatchObject({
      prefix: "lead_image",
      imageId: "7",
      origImage: "img/uploads/photo.jpg",
      value: "img/uploads/photo.jpg",
      deleted: false,
      preview: {
        url: "/media/img/_preview.jpg",
        width: "800",
        height: "500",
      },
    });
    expect(state.thumbs).toEqual([
      {
        id: "11",
        name: "main",
        width: 220,
        height: 180,
        url: "/m.jpg",
        tmp: true,
      },
    ]);
    bridge.destroy();
  });

  it("notifies subscribers when another script writes with .val()", async () => {
    const fixture = mountFixture({ withElement: false });
    const bridge = new FormsetBridge(fixture.root);
    const seen = vi.fn();
    bridge.subscribe(seen);

    (fixture.field("image") as HTMLInputElement).value = "img/other.jpg";

    await flush();
    expect(seen).toHaveBeenCalledTimes(1);
    expect(bridge.getSnapshot().origImage).toBe("img/other.jpg");
    bridge.destroy();
  });

  it("does not notify when nothing moved", async () => {
    const fixture = mountFixture({ withElement: false });
    const bridge = new FormsetBridge(fixture.root);
    const seen = vi.fn();
    bridge.subscribe(seen);

    (fixture.field("caption") as HTMLInputElement).value = "a caption";

    await flush();
    expect(seen).not.toHaveBeenCalled();
    bridge.destroy();
  });
});

describe("writeComplete", () => {
  it("writes the 4.x fields in the 4.x order", () => {
    const fixture = mountFixture({ withElement: false, initialForms: "1" });
    const bridge = new FormsetBridge(fixture.root);
    const order: string[] = [];
    fixture.root.addEventListener(
      "input",
      (event) => {
        order.push((event.target as HTMLInputElement).name);
      },
      true,
    );

    expect(bridge.writeComplete(payload())).toBe(true);

    expect(order).toEqual([
      "lead_image-0-id",
      "lead_image-0-image",
      "lead_image",
      "lead_image-TOTAL_FORMS",
    ]);
    expect((fixture.field("id") as HTMLInputElement).value).toBe("7");
    expect((fixture.field("image") as HTMLInputElement).value).toBe(
      "img/uploads/photo.jpg",
    );
    expect(fixture.dataField.value).toBe("img/uploads/photo.jpg");
    expect((fixture.field("TOTAL_FORMS") as HTMLInputElement).value).toBe("1");
    expect((fixture.field("INITIAL_FORMS") as HTMLInputElement).value).toBe(
      "1",
    );
    bridge.destroy();
  });

  it("zeroes INITIAL_FORMS when there is no image id", () => {
    const fixture = mountFixture({ withElement: false, initialForms: "1" });
    const bridge = new FormsetBridge(fixture.root);
    const order: string[] = [];
    fixture.root.addEventListener(
      "input",
      (event) => {
        order.push((event.target as HTMLInputElement).name);
      },
      true,
    );

    bridge.writeComplete(
      payload({ crop: { ...payload().crop, image_id: null } }),
    );

    expect(order).toEqual([
      "lead_image-0-id",
      "lead_image-INITIAL_FORMS",
      "lead_image-0-image",
      "lead_image",
      "lead_image-TOTAL_FORMS",
    ]);
    expect((fixture.field("INITIAL_FORMS") as HTMLInputElement).value).toBe(
      "0",
    );
    bridge.destroy();
  });

  it("stops before the thumbs when the payload has no thumbs list", () => {
    const fixture = mountFixture({ withElement: false });
    const bridge = new FormsetBridge(fixture.root);

    expect(
      bridge.writeComplete(
        payload({
          thumbs: undefined as unknown as LegacyCompletePayload["thumbs"],
        }),
      ),
    ).toBe(false);

    expect(fixture.field("thumbs")!.querySelectorAll("option")).toHaveLength(0);
    expect(bridge.getSnapshot().preview.url).toBe("/media/img/_preview.jpg");
    bridge.destroy();
  });

  it("can be told not to dispatch events", () => {
    const fixture = mountFixture({ withElement: false });
    const bridge = new FormsetBridge(fixture.root, {
      dispatchInputEvents: false,
    });
    const seen = vi.fn();
    fixture.root.addEventListener("input", seen, true);
    fixture.root.addEventListener("change", seen, true);

    bridge.writeComplete(payload());

    expect(seen).not.toHaveBeenCalled();
    expect(fixture.dataField.value).toBe("img/uploads/photo.jpg");
    bridge.destroy();
  });
});

describe("setThumbOptions", () => {
  it("emits the option attributes both 4.x and the server widget emit", () => {
    const fixture = mountFixture({
      withElement: false,
      thumbs: [{ id: 1, name: "stale", width: 1, height: 1 }],
    });
    const bridge = new FormsetBridge(fixture.root);

    bridge.setThumbOptions({
      main: { id: 11, name: "main", width: 220, height: 180, url: "/m.jpg" },
      skipped: { id: null, name: "skipped", width: 1, height: 1 },
      thumb: { id: 12, name: "thumb", width: 90, height: 60, url: "/t.jpg" },
    });

    const select = fixture.field("thumbs") as HTMLSelectElement;
    expect(select.innerHTML).toBe(
      '<option value="11" data-width="220" data-height="180" data-url="/m.jpg" data-tmp-file="true" selected="selected">main</option>' +
        '<option value="12" data-width="90" data-height="60" data-url="/t.jpg" data-tmp-file="true" selected="selected">thumb</option>',
    );
    expect([...select.selectedOptions].map((o) => o.value)).toEqual([
      "11",
      "12",
    ]);
    bridge.destroy();
  });
});
