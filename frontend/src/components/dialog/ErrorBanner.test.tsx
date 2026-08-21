/**
 * Verifies API messages are rendered as text and rewrites the reserved 501
 * response as guidance for the editor.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import { PER_SIZE_SOURCE_UNSUPPORTED } from "../../api/v1";
import {
  HEADSHOT_SIZES,
  headshotUpload,
} from "../../testing/canonicalFixtures";
import { apiError, mountDialog, stubFetch } from "../../testing/dialogHarness";
import { flush, waitFor } from "../../testing/fixtures";

const IMAGE = {
  id: 1,
  name: "author/headshots/{Y}/{m}/{DIR}/original.jpg",
  width: 674,
  height: 800,
};

function click(el: Element | null) {
  el?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
}

afterEach(async () => {
  document.body.innerHTML = "";
  vi.unstubAllGlobals();
  await flush(5);
});

/** Submit the current crop against a stubbed response. */
async function cropAgainst(body: unknown, status: number) {
  const dialog = await mountDialog({ sizes: HEADSHOT_SIZES, image: IMAGE });
  stubFetch(body, { status });
  click(dialog.find("crop-button"));
  await waitFor(() => dialog.find("error-container")?.hidden === false, {
    message: "the error banner",
  });
  return dialog;
}

describe("a failure the server sent prose for", () => {
  it("shows the message as text, on the crop step", async () => {
    const { find } = await cropAgainst(
      apiError("invalid", "sizes must be a list.", { field: "sizes" }),
      400,
    );
    const banner = find("error-container");

    expect(banner?.hidden).toBe(false);
    expect(banner?.getAttribute("role")).toBe("alert");
    expect(banner?.getAttribute("aria-atomic")).toBe("true");
    expect(banner?.textContent).toBe("sizes must be a list.");
    expect(find("cropbox")).not.toBeNull();
  });

  it("says nothing while nothing has failed", async () => {
    stubFetch(headshotUpload());
    const { find } = await mountDialog({ sizes: HEADSHOT_SIZES, image: IMAGE });

    expect(find("error-container")?.hidden).toBe(true);
    expect(find("error-container")?.textContent).toBe("");
  });
});

describe("a crop from a source that is not the image", () => {
  const refusal = apiError(
    PER_SIZE_SOURCE_UNSUPPORTED,
    "Cropping 'main' from a source other than the image being cropped is not implemented.",
    { field: "thumbs.main", details: { source: "other/original.jpg" } },
  );

  it("is worded for the editor, and names the size", async () => {
    const { find } = await cropAgainst(refusal, 501);
    const text = find("error-container")?.textContent ?? "";

    expect(find("error-container")?.hidden).toBe(false);
    expect(text).toContain("main");
    expect(text).not.toContain("not implemented");
    // Render the server message as text rather than HTML.
    expect(find("error-container")?.innerHTML).not.toContain("<a");
  });

  it("says the general thing when the refusal named no size", async () => {
    const { find } = await cropAgainst(
      apiError(PER_SIZE_SOURCE_UNSUPPORTED, "Not implemented."),
      501,
    );
    const text = find("error-container")?.textContent ?? "";

    expect(text).toContain("from the image itself");
    expect(text).not.toContain("Not implemented.");
  });
});
