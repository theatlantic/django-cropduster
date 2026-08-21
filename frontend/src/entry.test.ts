import { afterEach, describe, expect, it } from "vitest";

import { registry } from "./dom/registry";
import { cleanupDocument, waitFor, widgetHtml } from "./testing/fixtures";

afterEach(cleanupDocument);

describe("entry", () => {
  it("installs the global API, defines the element and mounts what is there", async () => {
    // The page is parsed before the bundle runs, and the debug flag rides on
    // the change form's query string.
    window.history.replaceState(
      {},
      "",
      "/admin/article/1/change/?cropduster_debug=1",
    );
    document.body.innerHTML =
      widgetHtml({ prefix: "lead_image" }) +
      widgetHtml({ prefix: "alt_image", withElement: false });

    await import("./entry");
    // The second widget's markup predates the custom element; rescan adopts it.
    await waitFor(
      () => registry.byPrefix("lead_image") && registry.byPrefix("alt_image"),
      { message: "both widgets to mount" },
    );

    expect(window.CropDuster).toBeDefined();
    expect(customElements.get("cropduster-widget")).toBeDefined();
    expect(document.body.classList.contains("cropduster-debug")).toBe(true);
  });
});
