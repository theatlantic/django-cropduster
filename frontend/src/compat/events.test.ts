import { afterEach, describe, expect, it, vi } from "vitest";

import { UPDATE_EVENT, bindRescanListeners, emitUpdate } from "./events";

interface TriggerCall {
  type: string;
  args: unknown[];
}

function fakeJQuery(log: TriggerCall[], handlers: Map<string, () => void>) {
  const $ = (() => ({
    data: () => undefined,
    trigger: (type: string, args: unknown[] = []) => {
      log.push({ type, args });
      handlers.get(type)?.();
    },
    on: (type: string, handler: () => void) => handlers.set(type, handler),
    off: (type: string) => handlers.delete(type),
  })) as unknown as { fn?: { jquery?: string } };
  $.fn = { jquery: "3.7.1" };
  return $;
}

const globals = globalThis as unknown as Record<string, unknown>;

afterEach(() => {
  delete globals.django;
  delete globals.grp;
  delete globals.jQuery;
  delete globals.$;
});

describe("emitUpdate", () => {
  it("dispatches natively and through every jQuery instance", () => {
    const log: TriggerCall[] = [];
    globals.django = { jQuery: fakeJQuery(log, new Map()) };
    globals.grp = { jQuery: fakeJQuery(log, new Map()) };
    const native = vi.fn();
    document.addEventListener(UPDATE_EVENT, native);

    emitUpdate("lead_image", { crop: { image_id: 7 } });

    expect(native).toHaveBeenCalledTimes(1);
    const event = native.mock.calls[0]?.[0] as CustomEvent;
    expect(event.detail).toEqual({
      prefix: "lead_image",
      data: { crop: { image_id: 7 } },
    });
    expect(event.bubbles).toBe(true);

    // jQuery listeners keep 4.x's positional (event, prefix, data) signature.
    expect(log).toEqual([
      { type: UPDATE_EVENT, args: ["lead_image", { crop: { image_id: 7 } }] },
      { type: UPDATE_EVENT, args: ["lead_image", { crop: { image_id: 7 } }] },
    ]);
    document.removeEventListener(UPDATE_EVENT, native);
  });

  it("reaches a real jQuery handler through both channels", async () => {
    const jQuery = (await import("jquery")).default;
    globals.django = { jQuery };
    const calls: unknown[][] = [];
    jQuery(document).trigger("noop");
    (
      jQuery(document) as unknown as {
        on(type: string, handler: (...args: unknown[]) => void): void;
        off(type: string): void;
      }
    ).on(UPDATE_EVENT, (...args: unknown[]) => calls.push(args));

    emitUpdate("lead_image", { crop: {} });

    // jQuery listens with addEventListener, so it also sees the native
    // dispatch, which includes no positional arguments. The second call is the
    // 4.x one. See the note in events.ts.
    expect(calls).toHaveLength(2);
    expect(calls[0]).toHaveLength(1);
    expect(calls[1]?.slice(1)).toEqual(["lead_image", { crop: {} }]);
    (jQuery(document) as unknown as { off(type: string): void }).off(
      UPDATE_EVENT,
    );
  });

  it("fires once when the page has one jQuery under several names", () => {
    const log: TriggerCall[] = [];
    const $ = fakeJQuery(log, new Map());
    globals.django = { jQuery: $ };
    globals.jQuery = $;
    globals.$ = $;

    emitUpdate("lead_image", null);

    expect(log).toHaveLength(1);
  });
});

describe("bindRescanListeners", () => {
  it("listens for the native formset:added on document", () => {
    const rescan = vi.fn();
    const unbind = bindRescanListeners(rescan);

    // nested-admin dispatches this on the new row; it bubbles to document.
    const row = document.createElement("div");
    document.body.appendChild(row);
    row.dispatchEvent(
      new CustomEvent("formset:added", {
        bubbles: true,
        detail: { formsetName: "photo_set" },
      }),
    );

    expect(rescan).toHaveBeenCalledTimes(1);
    unbind();
    row.dispatchEvent(new CustomEvent("formset:added", { bubbles: true }));
    expect(rescan).toHaveBeenCalledTimes(1);
    row.remove();
  });

  it("listens for djnesting events on every jQuery instance", () => {
    const log: TriggerCall[] = [];
    const djangoHandlers = new Map<string, () => void>();
    const grpHandlers = new Map<string, () => void>();
    const $django = fakeJQuery(log, djangoHandlers);
    const $grp = fakeJQuery(log, grpHandlers);
    globals.django = { jQuery: $django };
    globals.grp = { jQuery: $grp };
    const rescan = vi.fn();

    const unbind = bindRescanListeners(rescan);

    expect([...djangoHandlers.keys()]).toEqual([
      "djnesting:added",
      "djnesting:attrchange",
      "djnesting:initialized",
    ]);
    // A downstream event bridge forwards only a subset between the two
    // copies, so a widget bound to one instance would miss the other's
    // events.
    grpHandlers.get("djnesting:attrchange")?.();
    expect(rescan).toHaveBeenCalledTimes(1);

    unbind();
    expect(djangoHandlers.size).toBe(0);
    expect(grpHandlers.size).toBe(0);
  });
});
