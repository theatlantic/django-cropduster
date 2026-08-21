/** Mount the real page shell and component tree for dialog tests. */

import { vi } from "vitest";

import { mountPageShell } from "../components/dialog/shells/PageShell";
import { dialogConfigJson } from "./dialogFixtures";
import type { DialogConfigOptions } from "./dialogFixtures";
import { waitFor } from "./fixtures";

export interface OpenerStub {
  CropDuster?: { complete: ReturnType<typeof vi.fn> };
  [callback: string]: unknown;
}

export type ViewStub = Window & { close: ReturnType<typeof vi.fn> };

export function fakeView(opener: OpenerStub, search = ""): ViewStub {
  return {
    location: { search, pathname: "/cropduster/" },
    close: vi.fn(),
    opener,
  } as unknown as ViewStub;
}

export interface MountedDialog {
  host: HTMLElement;
  shadow: ShadowRoot;
  view: ViewStub;
  opener: OpenerStub;
  find<T extends HTMLElement>(id: string): T | null;
}

export async function mountDialog(
  options: DialogConfigOptions = {},
  opener: OpenerStub = { CropDuster: { complete: vi.fn() } },
): Promise<MountedDialog> {
  const host = document.createElement("div");
  host.id = "cropduster-app";
  host.setAttribute("data-config", dialogConfigJson(options));
  document.body.appendChild(host);

  const view = fakeView(opener);
  mountPageShell(host, { view });
  await waitFor(() => host.shadowRoot?.getElementById("id_image"), {
    message: "the dialog to render",
  });

  const shadow = host.shadowRoot!;
  return {
    host,
    shadow,
    view,
    opener,
    find: <T extends HTMLElement>(id: string) =>
      shadow.getElementById(id) as T | null,
  };
}

export function stubFetch(
  body: unknown,
  init: { ok?: boolean; status?: number } = {},
) {
  const status = init.status ?? (init.ok === false ? 400 : 200);
  const fetchMock = vi.fn(() =>
    Promise.resolve({
      ok: init.ok ?? status < 400,
      status,
      json: () => Promise.resolve(body),
    } as Response),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

/** Return each response in order, repeating the final one. */
export function stubFetchSequence(bodies: unknown[]) {
  let call = 0;
  const fetchMock = vi.fn<
    (url: string, init?: RequestInit) => Promise<Response>
  >(() => {
    const body = bodies[Math.min(call, bodies.length - 1)];
    call += 1;
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () => Promise.resolve(body),
    } as Response);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

/** Build the v1 API error object used by all endpoints. */
export function apiError(
  code: string,
  message: string,
  extra: { field?: string; details?: unknown } = {},
) {
  return {
    error: {
      code,
      message,
      field: extra.field ?? null,
      details: extra.details ?? null,
    },
  };
}

/** jsdom never loads an image, so the preview's dimensions are supplied. */
export function loadPreview(
  img: HTMLImageElement,
  width: number,
  height: number,
): void {
  Object.defineProperty(img, "naturalWidth", { value: width, writable: true });
  Object.defineProperty(img, "naturalHeight", {
    value: height,
    writable: true,
  });
  img.dispatchEvent(new Event("load"));
}

/** Assign a file to an input and dispatch its change event. */
export function chooseFile(input: HTMLInputElement, name = "img.jpg"): void {
  Object.defineProperty(input, "files", {
    value: [new File(["x"], name)],
    configurable: true,
  });
  input.dispatchEvent(new Event("change", { bubbles: true }));
}

/**
 * Update a text input through its native setter, then dispatch the input and
 * focusout events React listens for inside the shadow root.
 */
export function typeAndBlur(input: HTMLInputElement, value: string): void {
  const setter = Object.getOwnPropertyDescriptor(
    HTMLInputElement.prototype,
    "value",
  )?.set;
  setter?.call(input, value);
  input.dispatchEvent(new Event("input", { bubbles: true }));
  input.dispatchEvent(new FocusEvent("focusout", { bubbles: true }));
}
