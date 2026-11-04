/**
 * Verify prefix changes, direct property writes, input replacement, and
 * `CropDuster.complete()` write order against generated markup.
 */

import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import jQuery from "jquery";

import { FormsetBridge } from "./FormsetBridge";
import type { LegacyCompletePayload } from "./legacyPayload";
import { defineWidgetElement } from "../dom/CropDusterWidgetElement";
import { registry } from "../dom/registry";
import type { WidgetHandle } from "../dom/registry";
import { cleanupDocument, flush, waitFor } from "../testing/fixtures";
import { loadFixture } from "../testing/htmlFixtures";
import { cloneTemplateRow, renameRow } from "../testing/nestedAdmin";
import { recordWrites } from "../testing/writeLog";

const globals = globalThis as unknown as Record<string, unknown>;

const ORIGINAL = "article/lead_image/{Y}/{m}/img/original.jpg";

beforeAll(() => {
  defineWidgetElement();
});

afterEach(async () => {
  await cleanupDocument();
  delete globals.django;
  delete globals.grp;
  delete globals.jQuery;
  delete globals.$;
});

function mounted(prefix: string): Promise<WidgetHandle> {
  return waitFor(() => registry.byPrefix(prefix), {
    message: `a widget at ${prefix}`,
  });
}

function payload(
  overrides: Partial<LegacyCompletePayload> = {},
): LegacyCompletePayload {
  return {
    crop: {
      image_id: 9,
      orig_image: "article/lead_image/2026/09/new/original.jpg",
      orig_w: 674,
      orig_h: 800,
      thumbs: {
        main: {
          id: 41,
          name: "main",
          width: 600,
          height: 480,
          url: "/media/article/lead_image/2026/09/new/main.jpg",
        },
        thumb: {
          id: 42,
          name: "thumb",
          width: 110,
          height: 90,
          url: "/media/article/lead_image/2026/09/new/thumb.jpg",
        },
      },
    },
    thumbs: [],
    initial: true,
    preview_url: "/media/article/lead_image/2026/09/new/_preview.jpg",
    preview_w: 421,
    preview_h: 500,
    ...overrides,
  };
}

describe("prefixes are re-derived, never remembered", () => {
  /** Two item rows of a nested inline, mounted, ready to be renumbered. */
  async function items(): Promise<HTMLElement[]> {
    const fixture = loadFixture("nested_empty_item");
    const outer = document.createElement("div");
    outer.className = "djn-inline-form";
    outer.id = "section_set-empty";
    const inner = document.createElement("div");
    inner.className = "djn-inline-form";
    inner.id = "section_set-empty-items-empty";
    inner.append(...fixture.roots);
    outer.appendChild(inner);
    document.body.appendChild(outer);

    const section = cloneTemplateRow(outer, "section_set", 0);
    document.body.appendChild(section);
    const template = section.querySelector<HTMLElement>(
      "#section_set-0-items-empty",
    )!;
    const rows = [0, 1].map((index) => {
      const row = cloneTemplateRow(template, "section_set-0-items", index);
      document.body.appendChild(row);
      return row;
    });
    await flush();
    return rows;
  }

  it("follows a _fillGap rename to the new names", async () => {
    const [first, second] = await items();
    const widget = await mounted("section_set-0-items-1-image");
    const bridge = widget.bridge;

    // Removing row 0 renumbers row 1 down, through the same non-global,
    // lookahead-guarded regex nested-admin uses.
    first!.remove();
    renameRow(second!, "section_set-0-items", 1, 0);
    await waitFor(() => bridge.prefix === "section_set-0-items-0-image", {
      message: "the bridge to follow the rename",
    });

    expect(bridge.root.id).toBe("section_set-0-items-0-image-group");
    expect(bridge.root.id).toBe("section_set-0-items-0-image-group");

    const imageField = bridge.field("image");
    expect(imageField?.getAttribute("name")).toBe(
      "section_set-0-items-0-image-0-image",
    );
    expect(bridge.mgmt("TOTAL_FORMS")?.getAttribute("name")).toBe(
      "section_set-0-items-0-image-TOTAL_FORMS",
    );
    // Nothing at the old names survives to be read by mistake.
    expect(bridge.byName("section_set-0-items-1-image-0-image")).toBeNull();

    bridge.writeComplete(payload());

    expect(imageField?.value).toBe(
      "article/lead_image/2026/09/new/original.jpg",
    );
    expect(bridge.dataField?.value).toBe(
      "article/lead_image/2026/09/new/original.jpg",
    );
    expect(bridge.field("id")?.value).toBe("9");
    // And the compat layer, which receives a bare prefix, resolves the same
    // widget under its new name and no longer under the old one.
    expect(registry.byPrefix("section_set-0-items-0-image")).toBe(widget);
    expect(registry.byPrefix("section_set-0-items-1-image")).toBeNull();
  });

  it("keeps the two fields of one row apart across a rename", async () => {
    const [, second] = await items();
    const image = await mounted("section_set-0-items-1-image");
    const alt = await mounted("section_set-0-items-1-alt_image");

    renameRow(second!, "section_set-0-items", 1, 0);
    await waitFor(() => image.bridge.prefix === "section_set-0-items-0-image", {
      message: "the bridge to follow the rename",
    });

    image.bridge.writeComplete(payload());

    expect(image.bridge.field("image")?.value).toBe(
      "article/lead_image/2026/09/new/original.jpg",
    );
    expect(alt.bridge.field("image")?.value).toBe("");
    expect(alt.bridge.prefix).toBe("section_set-0-items-0-alt_image");
  });
});

describe("writes from other scripts", () => {
  it("notices a jQuery .val() on a formset input", async () => {
    globals.django = { jQuery };
    const fixture = loadFixture("article_change_lead_and_alt");
    const widget = await mounted("lead_image");
    const seen = vi.fn();
    widget.bridge.subscribe(seen);

    // Downstream scripts write exactly this way: a property assignment, no
    // event, attribute untouched.
    jQuery(fixture.field("lead_image", "image")).val("article/other.jpg");
    expect(fixture.field("lead_image", "image").getAttribute("value")).toBe(
      ORIGINAL,
    );

    await waitFor(
      () => widget.bridge.getSnapshot().origImage === "article/other.jpg",
      { message: "the property write to be noticed" },
    );

    expect(seen).toHaveBeenCalledTimes(1);
  });

  it("notices the DELETE checkbox nested-admin's cascade ticks", async () => {
    globals.django = { jQuery };
    const fixture = loadFixture("article_change_lead_and_alt");
    const widget = await mounted("lead_image");
    const root = fixture.root("lead_image");
    expect(root.classList.contains("predelete")).toBe(false);

    // Use the assignments from jquery.djangoformset.js:269-276.
    const checkbox = fixture.field("lead_image", "DELETE");
    jQuery(checkbox).attr("checked", "checked");
    checkbox.checked = true;
    await waitFor(() => widget.bridge.getSnapshot().deleted, {
      message: "the DELETE tick to be noticed",
    });

    expect(root.classList.contains("predelete")).toBe(true);
    expect(root.classList.contains("grp-predelete")).toBe(true);
  });

  it("re-reads and re-shims after the inputs are replaced wholesale", async () => {
    globals.django = { jQuery };
    const fixture = loadFixture("article_change_lead_and_alt");
    const widget = await mounted("lead_image");
    const root = fixture.root("lead_image");
    const seen = vi.fn();
    widget.bridge.subscribe(seen);

    // A revert rebuilds the form's controls from stored attributes. The shims
    // installed on the old elements go with them, so the only thing that can
    // save the widget is noticing the childList mutation and starting again.
    revertInputs(root);
    await waitFor(() => widget.bridge.readState().origImage === ORIGINAL, {
      message: "the bridge to re-derive from the rebuilt inputs",
    });

    expect(widget.bridge.prefix).toBe("lead_image");
    expect(widget.bridge.readState().origImage).toBe(ORIGINAL);
    expect(widget.bridge.readState().imageId).toBe("1");
    expect(widget.bridge.readState().thumbs.map((thumb) => thumb.id)).toEqual([
      "1",
      "2",
      "3",
    ]);

    seen.mockClear();
    jQuery(root.querySelector('[name="lead_image-0-image"]')!).val(
      "article/reverted.jpg",
    );
    await waitFor(
      () => widget.bridge.getSnapshot().origImage === "article/reverted.jpg",
      { message: "the write to the rebuilt input to be noticed" },
    );

    expect(seen).toHaveBeenCalledTimes(1);
  });

  it("survives django-autosave's revert, which takes the inputs away", async () => {
    globals.django = { jQuery };
    const fixture = loadFixture("article_change_lead_and_alt");
    const widget = await mounted("lead_image");
    const root = fixture.root("lead_image");

    // autosave.js:74-86 removes every `:input` in the *form* and appends the
    // replacements to the form, not back where they came from, then submits.
    // No controls remain to read; this path only needs to avoid throwing.
    for (const el of root.querySelectorAll("input,select,textarea")) {
      el.remove();
    }
    await waitFor(() => widget.bridge.prefix === null, {
      message: "the bridge to notice it has nothing left",
    });

    expect(widget.bridge.readState()).toMatchObject({
      imageId: "",
      origImage: "",
      value: "",
      thumbs: [],
      deleted: false,
    });
    expect(root.isConnected).toBe(true);
    expect(registry.byRoot(root)).toBe(widget);
  });
});

/** Delete every control under `root` and rebuild it from its attributes. */
function revertInputs(root: HTMLElement) {
  const controls = [...root.querySelectorAll("input,select,textarea")];
  const specs = controls.map((el) => ({
    tag: el.tagName.toLowerCase(),
    attributes: [...el.attributes].map((attr) => [attr.name, attr.value]),
    value: (el as HTMLInputElement).value,
    html: el.innerHTML,
    parent: el.parentElement!,
  }));
  for (const el of controls) {
    el.remove();
  }
  for (const spec of specs) {
    const el = document.createElement(spec.tag);
    for (const [name, value] of spec.attributes) {
      el.setAttribute(name!, value!);
    }
    el.innerHTML = spec.html;
    if (el instanceof HTMLInputElement) {
      el.value = spec.value;
    }
    spec.parent.appendChild(el);
  }
}

describe("writeComplete", () => {
  it("writes 4.x's fields in 4.x's order", async () => {
    const fixture = loadFixture("article_change_lead_and_alt");
    const widget = await mounted("lead_image");
    const log = recordWrites(fixture.root("lead_image"));

    widget.bridge.writeComplete(payload());
    log.stop();

    expect(log.entries).toEqual([
      "value lead_image-0-id=9",
      "value lead_image-0-image=article/lead_image/2026/09/new/original.jpg",
      "value lead_image=article/lead_image/2026/09/new/original.jpg",
      "value lead_image-TOTAL_FORMS=1",
      "option -1",
      "option -2",
      "option -3",
      "option +41",
      "option +42",
    ]);
  });

  it("zeroes INITIAL_FORMS between the id and the image, only when unsaved", async () => {
    const fixture = loadFixture("article_change_lead_and_alt");
    const widget = await mounted("alt_image");
    const log = recordWrites(fixture.root("alt_image"));

    widget.bridge.writeComplete(
      payload({ crop: { ...payload().crop, image_id: null } }),
    );
    log.stop();

    expect(log.entries.slice(0, 5)).toEqual([
      "value alt_image-0-id=",
      "value alt_image-INITIAL_FORMS=0",
      "value alt_image-0-image=article/lead_image/2026/09/new/original.jpg",
      "value alt_image=article/lead_image/2026/09/new/original.jpg",
      "value alt_image-TOTAL_FORMS=1",
    ]);
  });

  it("stops before the thumbs when the payload has no thumbs list", async () => {
    const fixture = loadFixture("article_change_lead_and_alt");
    const widget = await mounted("lead_image");
    const log = recordWrites(fixture.root("lead_image"));

    const wrote = widget.bridge.writeComplete(
      payload({
        thumbs: undefined as unknown as LegacyCompletePayload["thumbs"],
      }),
    );
    log.stop();

    expect(wrote).toBe(false);
    expect(log.entries.filter((entry) => entry.startsWith("option"))).toEqual(
      [],
    );
    // The saved options are still the ones the server rendered.
    expect(widget.bridge.readThumbs().map((thumb) => thumb.name)).toEqual([
      "main",
      "thumb",
      "no_height",
    ]);
  });

  it("works on a form no widget was ever mounted on", async () => {
    const fixture = loadFixture("author_add_headshot");
    fixture.host("headshot").remove();
    await flush();
    expect(registry.byPrefix("headshot")).toBeNull();

    const bridge = new FormsetBridge(fixture.root("headshot"), {
      observe: false,
    });
    expect(bridge.writeComplete(payload())).toBe(true);
    expect(fixture.field("headshot", "id").value).toBe("9");
    expect(bridge.readThumbs().map((thumb) => thumb.id)).toEqual(["41", "42"]);
  });
});
