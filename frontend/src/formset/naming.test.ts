import { describe, expect, it } from "vitest";

import {
  derivePrefix,
  fieldId,
  isTemplatePrefix,
  joinField,
  managementField,
} from "./naming";
import type { PrefixRootLike } from "./naming";

describe("isTemplatePrefix", () => {
  it("accepts real rows", () => {
    for (const prefix of [
      "lead_image",
      "article_set-0-lead_image",
      "sections-0-items-12-image",
      "image-0-image",
      "empty",
      "empty_field",
      "gallery-3-empty_slot",
    ]) {
      expect(isTemplatePrefix(prefix), prefix).toBe(false);
    }
  });

  it("rejects Django's __prefix__ template", () => {
    for (const prefix of [
      "__prefix__",
      "article_set-__prefix__-lead_image",
      "sections-0-items-__prefix__-image",
      "sections-__prefix__-items-__prefix__-image",
    ]) {
      expect(isTemplatePrefix(prefix), prefix).toBe(true);
    }
  });

  it("rejects the -empty container ids, polymorphic ones included", () => {
    for (const prefix of [
      "article_set-empty",
      "sections-0-items-empty",
      "article_set-empty-lead_image",
      // Polymorphic templates include the content type id.
      "sections-0-items-empty-27",
      "sections-0-items-empty-27-image",
    ]) {
      expect(isTemplatePrefix(prefix), prefix).toBe(true);
    }
  });

  it("treats a missing prefix as a real row's absence, not a template", () => {
    expect(isTemplatePrefix("")).toBe(false);
    expect(isTemplatePrefix(null)).toBe(false);
    expect(isTemplatePrefix(undefined)).toBe(false);
  });
});

describe("derivePrefix", () => {
  function widget(html: string): Element {
    const root = document.createElement("div");
    root.className = "module cropduster-form nested-inline-form";
    root.innerHTML = html;
    return root;
  }

  it("reads the name off the data field", () => {
    const root = widget(
      '<input type="hidden" id="id_lead_image-0-id" name="lead_image-0-id">' +
        '<input type="text" id="id_lead_image" name="lead_image"' +
        ' class="cropduster-data-field cropduster-text-field">',
    );
    expect(derivePrefix(root)).toBe("lead_image");
  });

  it("follows a renamed row", () => {
    const root = widget(
      '<input class="cropduster-data-field" id="id_sections-0-items-__prefix__-image"' +
        ' name="sections-0-items-__prefix__-image">',
    );
    const field = root.querySelector(".cropduster-data-field");
    expect(derivePrefix(root)).toBe("sections-0-items-__prefix__-image");
    field?.setAttribute("name", "sections-0-items-4-image");
    expect(derivePrefix(root)).toBe("sections-0-items-4-image");
  });

  it("returns null when there is no data field or no name", () => {
    expect(derivePrefix(widget("<span></span>"))).toBeNull();
    expect(derivePrefix(widget('<input class="cropduster-data-field">'))).toBe(
      null,
    );
    expect(
      derivePrefix(widget('<input class="cropduster-data-field" name="">')),
    ).toBeNull();
  });

  it("works against anything that can resolve a selector", () => {
    const root: PrefixRootLike = {
      querySelector: () => ({ getAttribute: () => "lead_image" }),
    };
    expect(derivePrefix(root)).toBe("lead_image");
  });
});

describe("field names", () => {
  it("builds row field names", () => {
    expect(joinField("lead_image", 0, "image")).toBe("lead_image-0-image");
    expect(joinField("sections-0-items-4-image", 0, "thumbs")).toBe(
      "sections-0-items-4-image-0-thumbs",
    );
    expect(joinField("lead_image", "__prefix__", "id")).toBe(
      "lead_image-__prefix__-id",
    );
  });

  it("builds management field names", () => {
    expect(managementField("lead_image", "TOTAL_FORMS")).toBe(
      "lead_image-TOTAL_FORMS",
    );
    expect(managementField("lead_image", "INITIAL_FORMS")).toBe(
      "lead_image-INITIAL_FORMS",
    );
  });

  it("builds ids the way Django renders them", () => {
    expect(fieldId("lead_image")).toBe("id_lead_image");
    expect(fieldId(joinField("lead_image", 0, "id"))).toBe(
      "id_lead_image-0-id",
    );
  });
});
