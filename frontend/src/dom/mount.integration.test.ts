/**
 * Verify mounting and renaming against generated admin HTML and the
 * django-nested-admin row helpers.
 */

import { afterEach, beforeAll, describe, expect, it } from "vitest";

import {
  CropDusterWidgetElement,
  defineWidgetElement,
} from "./CropDusterWidgetElement";
import { registry } from "./registry";
import {
  cardQuery,
  cardQueryAll,
  cleanupDocument,
  flush,
  waitFor,
  waitForWidget,
} from "../testing/fixtures";
import { FIXTURE_PREFIXES, loadFixture } from "../testing/htmlFixtures";
import { cloneTemplateRow, renameRow } from "../testing/nestedAdmin";

beforeAll(() => {
  defineWidgetElement();
});

afterEach(cleanupDocument);

function upgraded(el: Element | null): CropDusterWidgetElement {
  if (!(el instanceof CropDusterWidgetElement)) {
    throw new Error("<cropduster-widget> did not upgrade");
  }
  return el;
}

/** Every `.cropduster-button` under an element: one per mount, never two. */
function buttons(scope: ParentNode): Element[] {
  return [...scope.querySelectorAll(".cropduster-button")];
}

/**
 * The nested rows that contain an empty-form fixture.
 *
 * `nested_empty_item` is rendered inside the *outer* group's template, so its
 * prefixes contain both placeholders: `section_set-empty-items-__prefix__-`.
 * Reaching a real row therefore takes the two `add()` calls a user would make,
 * one per level.
 */
function nestedTemplates(roots: HTMLElement[]): HTMLElement {
  const outer = document.createElement("div");
  outer.className = "djn-inline-form";
  outer.id = "section_set-empty";
  const inner = document.createElement("div");
  inner.className = "djn-inline-form";
  inner.id = "section_set-empty-items-empty";
  inner.append(...roots);
  outer.appendChild(inner);
  document.body.appendChild(outer);
  return outer;
}

/** `add()` on the outer group, then on the inner one. */
function addItemRow(outerTemplate: HTMLElement, index: number): HTMLElement {
  const section = cloneTemplateRow(outerTemplate, "section_set", 0);
  document.body.appendChild(section);
  const innerTemplate = section.querySelector<HTMLElement>(
    "#section_set-0-items-empty",
  )!;
  const item = cloneTemplateRow(innerTemplate, "section_set-0-items", index);
  document.body.appendChild(item);
  return item;
}

describe("the rendered widget", () => {
  it("mounts every widget of an add form", async () => {
    const fixture = loadFixture("author_add_headshot");
    await flush(0);

    const widget = registry.byPrefix("headshot");
    expect(widget).not.toBeNull();
    expect(widget?.root).toBe(fixture.root("headshot"));
    expect(upgraded(fixture.host("headshot")).widget).toBe(widget);
  });

  it("mounts both fields of a change form independently", async () => {
    const fixture = loadFixture("article_change_lead_and_alt");
    await flush(0);

    const lead = registry.byPrefix("lead_image");
    const alt = registry.byPrefix("alt_image");
    expect(lead).not.toBeNull();
    expect(alt).not.toBeNull();
    expect(lead).not.toBe(alt);
    expect(lead?.root).toBe(fixture.root("lead_image"));
    expect(alt?.root).toBe(fixture.root("alt_image"));

    // Each widget's bridge sees only its own formset, though both prefixes are
    // in the same container and one is a prefix of nothing the other owns.
    expect(lead?.bridge.readState().origImage).toBe(
      "article/lead_image/{Y}/{m}/img/original.jpg",
    );
    expect(alt?.bridge.readState().origImage).toBe("");
  });

  it("renders the button into the server-rendered anchor, in place", async () => {
    const fixture = loadFixture("author_add_headshot");
    const root = fixture.root("headshot");
    await waitForWidget(root);

    const anchor = root.querySelector(".cropduster-customfield")!;
    const button = anchor.querySelector(".cropduster-button");
    expect(button).not.toBeNull();
    expect(button?.textContent).toBe("Upload Image");
    expect(buttons(root)).toHaveLength(1);

    // The three elements downstream stylesheets select across keep their
    // order: data field, then the widget element, then the anchor.
    const order = [...root.children].filter((child) =>
      child.matches(
        ".cropduster-data-field,cropduster-widget,.cropduster-customfield",
      ),
    );
    expect(order.map((el) => el.tagName.toLowerCase())).toEqual([
      "input",
      "cropduster-widget",
      "a",
    ]);
  });

  it("renders the saved preview into the server-rendered thumbs div", async () => {
    const fixture = loadFixture("article_change_lead_and_alt");
    const images = fixture
      .root("lead_image")
      .querySelector<HTMLElement>(".cropduster-images")!;
    const anchor = await waitFor(
      () => cardQuery<HTMLAnchorElement>(images, "a"),
      { message: "the saved preview to render" },
    );

    expect(anchor.className).toBe("cropduster-image cropduster-image-preview");
    expect(anchor.getAttribute("href")).toBe(
      "/media/article/lead_image/{Y}/{m}/img/_preview.jpg",
    );
    const img = anchor.querySelector("img")!;
    expect(img.className).toBe(
      "cropduster-image-thumb cropduster-image-thumb-preview",
    );
    expect(img.getAttribute("src")).toBe(
      "/media/article/lead_image/{Y}/{m}/img/_preview.jpg?mod={MOD}",
    );
    expect(img.hasAttribute("srcset")).toBe(false);
    expect(img.getAttribute("width")).toBe("421");
    expect(img.getAttribute("height")).toBe("500");
  });
});

describe("a row the parser has not finished", () => {
  /**
   * On a change form the bundle is a plain `<script src>` in the head, so it
   * runs while the document is still being parsed and this element upgrades
   * the moment its start tag is read, ahead of the anchor and the thumbnail
   * container that follow it in the same wrapper. Mounting there would give
   * React two portals into nothing and never render anything again.
   */
  function loading(): () => void {
    Object.defineProperty(document, "readyState", {
      configurable: true,
      get: () => "loading",
    });
    return () => Reflect.deleteProperty(document, "readyState");
  }

  it("waits for the containers, then mounts", async () => {
    const done = loading();
    try {
      const fixture = loadFixture("author_add_headshot");
      const root = fixture.root("headshot");
      const anchor = root.querySelector<HTMLElement>(
        ".cropduster-customfield",
      )!;
      const group = root.querySelector<HTMLElement>(".cropduster-image-group")!;
      anchor.remove();
      group.remove();
      await flush();

      expect(registry.byPrefix("headshot")).toBeNull();

      root.appendChild(anchor);
      await flush();
      // The anchor alone is not enough: the thumbnails have nowhere to go.
      expect(registry.byPrefix("headshot")).toBeNull();

      root.appendChild(group);
      await waitForWidget(root);

      expect(registry.byPrefix("headshot")).not.toBeNull();
      expect(buttons(root)).toHaveLength(1);
      expect(anchor.querySelector(".cropduster-button")).not.toBeNull();
    } finally {
      done();
    }
  });

  it("mounts anyway once the document is loaded, containers or not", async () => {
    const fixture = loadFixture("author_add_headshot");
    const root = fixture.root("headshot");
    root.querySelector(".cropduster-image-group")!.remove();
    await waitForWidget(root);

    // Waiting past the end of the document would be waiting forever, and
    // markup that predates the template is entitled to be missing pieces.
    expect(registry.byPrefix("headshot")).not.toBeNull();
    expect(buttons(root)).toHaveLength(1);
  });
});

describe("the empty-form template", () => {
  it("does not mount, at either of its two placeholder prefixes", async () => {
    const fixture = loadFixture("nested_empty_item");
    const before = fixture.container.innerHTML;
    await flush();

    for (const prefix of FIXTURE_PREFIXES.nested_empty_item) {
      expect(prefix).toMatch(/__prefix__/);
      expect(upgraded(fixture.host(prefix)).widget).toBeNull();
      expect(registry.byPrefix(prefix)).toBeNull();
    }
    expect(registry.all()).toHaveLength(0);
    // Untouched, down to the server-rendered button React would otherwise
    // have replaced: an unmounted template is inert markup.
    expect(fixture.container.innerHTML).toBe(before);
  });

  it("mounts once add() has renamed the clone", async () => {
    const fixture = loadFixture("nested_empty_item");
    const outer = nestedTemplates(fixture.roots);
    await flush();
    expect(registry.all()).toHaveLength(0);

    const section = cloneTemplateRow(outer, "section_set", 0);
    document.body.appendChild(section);
    await flush();
    // Still a template: only the outer half of the prefix has been renamed.
    expect(registry.all()).toHaveLength(0);

    const template = section.querySelector<HTMLElement>(
      "#section_set-0-items-empty",
    )!;
    const item = cloneTemplateRow(template, "section_set-0-items", 0);
    document.body.appendChild(item);
    await waitFor(() => buttons(item).length === 2, {
      message: "both of the row's widgets to mount",
    });

    expect(registry.all()).toHaveLength(2);
    for (const field of ["image", "alt_image"]) {
      const prefix = `section_set-0-items-0-${field}`;
      const widget = registry.byPrefix(prefix);
      expect(widget, prefix).not.toBeNull();
      expect(item.contains(widget!.root)).toBe(true);
      expect(widget!.root.id).toBe(`${prefix}-group`);
    }
    expect(buttons(item)).toHaveLength(2);
  });
});

describe("cloning a mounted row", () => {
  /**
   * The 4.x `add()` clone inherited its click handler. A React clone instead
   * mounts a new root while leaving the original mounted.
   */
  async function mountedItem(): Promise<HTMLElement> {
    const fixture = loadFixture("nested_empty_item");
    const item = addItemRow(nestedTemplates(fixture.roots), 0);
    await waitFor(() => buttons(item).length === 2, {
      message: "both of the row's widgets to mount",
    });
    return item;
  }

  it("upgrades the clone fresh and leaves the original mounted", async () => {
    const first = await mountedItem();
    const original = registry.byPrefix("section_set-0-items-0-image");
    expect(original).not.toBeNull();

    const clone = first.cloneNode(true) as HTMLElement;
    // The copied markup has no widget until the clone is connected.
    expect(
      upgraded(clone.querySelector("cropduster-widget")).widget,
    ).toBeNull();

    document.body.appendChild(clone);
    renameRow(clone, "section_set-0-items", 0, 1);
    await waitFor(() => buttons(clone).length === 2, {
      message: "the clone's widgets to mount",
    });

    const moved = registry.byPrefix("section_set-0-items-1-image");
    expect(moved).not.toBeNull();
    expect(moved).not.toBe(original);
    expect(clone.contains(moved!.root)).toBe(true);

    // The original is untouched: same widget, still mounted, still one button.
    expect(registry.byPrefix("section_set-0-items-0-image")).toBe(original);
    expect(buttons(first)).toHaveLength(2);
    expect(buttons(clone)).toHaveLength(2);
    expect(registry.all()).toHaveLength(4);
  });

  it("leaves no dead root behind: the clone renders from its own formset", async () => {
    const first = await mountedItem();
    const clone = first.cloneNode(true) as HTMLElement;
    document.body.appendChild(clone);
    renameRow(clone, "section_set-0-items", 0, 1);
    await waitFor(() => buttons(clone).length === 2, {
      message: "the clone's widgets to mount",
    });

    const original = registry.byPrefix("section_set-0-items-0-image")!;
    const moved = registry.byPrefix("section_set-0-items-1-image")!;

    original.bridge.writeComplete({
      crop: {
        image_id: 7,
        orig_image: "nested/item/2026/08/a/original.jpg",
        orig_w: 800,
        orig_h: 600,
        thumbs: {},
      },
      thumbs: [],
      initial: true,
      preview_url: "/media/nested/item/2026/08/a/_preview.jpg",
      preview_w: 400,
      preview_h: 300,
    });

    const rendered = (row: HTMLElement) => {
      const images = row.querySelector<HTMLElement>(".cropduster-images");
      return images
        ? cardQueryAll(images, ".cropduster-image-thumb").map((img) =>
            img.getAttribute("src"),
          )
        : [];
    };
    await waitFor(() => rendered(first).length === 1, {
      message: "the crop to render in the original row",
    });
    expect(rendered(first)).toEqual([
      "/media/nested/item/2026/08/a/_preview.jpg",
    ]);
    expect(rendered(clone)).toEqual([]);
    expect(moved.bridge.readState().origImage).toBe("");
  });

  it("keeps data-config unchanged across the rename", async () => {
    const first = await mountedItem();
    const clone = first.cloneNode(true) as HTMLElement;
    document.body.appendChild(clone);
    renameRow(clone, "section_set-0-items", 0, 1);
    await flush();

    // nested-admin does not rewrite <cropduster-widget>, so its configuration
    // must not contain a prefix.
    const config = (row: HTMLElement) =>
      [...row.querySelectorAll("cropduster-widget")].map((el) =>
        el.getAttribute("data-config"),
      );
    expect(config(clone)).toEqual(config(first));
    for (const raw of config(clone)) {
      expect(raw).not.toMatch(/-(?:\d+|empty|__prefix__)-/);
    }
  });
});
