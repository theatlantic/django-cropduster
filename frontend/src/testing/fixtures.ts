/**
 * Minimal widget markup for unit tests.
 *
 * Integration tests use HTML rendered by Django; these fixtures let a unit
 * test vary one prefix, option, or missing element without loading an admin
 * page.
 */

export interface ThumbOptionFixture {
  id: string | number;
  name: string;
  width?: number | string;
  height?: number | string;
  url?: string;
  rendererUrl?: string;
  rendererSrcset?: string;
  tmp?: boolean;
  selected?: boolean;
}

export interface WidgetFixtureOptions {
  prefix?: string;
  /** The stored file name, in both `{prefix}` and `{prefix}-0-image`. */
  image?: string;
  imageId?: string;
  sizes?: unknown[];
  previewUrl?: string;
  previewRendererUrl?: string;
  previewSrcset?: string;
  previewW?: number | string;
  previewH?: number | string;
  origW?: number | string;
  origH?: number | string;
  uploadTo?: string;
  mediaUrl?: string;
  cropdusterUrl?: string;
  thumbs?: ThumbOptionFixture[];
  config?: Record<string, unknown> | null;
  /** Emit the `<cropduster-widget>` element (5.0 markup). */
  withElement?: boolean;
  /** Wrap in the admin row the 4.x click handler resolves through. */
  withRow?: boolean;
  totalForms?: string;
  initialForms?: string;
  deleted?: boolean;
}

const DEFAULTS = {
  prefix: "lead_image",
  image: "",
  imageId: "",
  sizes: [{ name: "main", w: 100, h: 50 }],
  previewUrl: "/media/img/_preview.jpg",
  previewW: 800,
  previewH: 500,
  origW: "" as number | string,
  origH: "" as number | string,
  uploadTo: "img/uploads",
  mediaUrl: "/media/",
  cropdusterUrl: "/cropduster/?pop=1",
  thumbs: [] as ThumbOptionFixture[],
  withElement: true,
  withRow: true,
  totalForms: "1",
  initialForms: "1",
  deleted: false,
};

function attr(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function optionHtml(thumb: ThumbOptionFixture): string {
  const parts = [`value="${attr(String(thumb.id))}"`];
  if (thumb.width !== undefined) {
    parts.push(`data-width="${attr(String(thumb.width))}"`);
  }
  if (thumb.height !== undefined) {
    parts.push(`data-height="${attr(String(thumb.height))}"`);
  }
  if (thumb.url !== undefined) {
    parts.push(`data-url="${attr(thumb.url)}"`);
  }
  if (thumb.rendererUrl !== undefined) {
    parts.push(`data-renderer-url="${attr(thumb.rendererUrl)}"`);
  }
  if (thumb.rendererSrcset !== undefined) {
    parts.push(`data-renderer-srcset="${attr(thumb.rendererSrcset)}"`);
  }
  if (thumb.tmp !== false) {
    parts.push('data-tmp-file="true"');
  }
  if (thumb.selected !== false) {
    parts.push('selected="selected"');
  }
  return `<option ${parts.join(" ")}>${thumb.name}</option>`;
}

/** The markup one widget renders as. */
export function widgetHtml(options: WidgetFixtureOptions = {}): string {
  const o = { ...DEFAULTS, ...options };
  const prefix = o.prefix;
  const config =
    options.config === null
      ? ""
      : ` data-config="${attr(
          JSON.stringify({
            uploadTo: o.uploadTo,
            mediaUrl: o.mediaUrl,
            ...(options.config ?? {}),
          }),
        )}"`;
  const element = o.withElement
    ? `<cropduster-widget${config}></cropduster-widget>`
    : "";
  const form = `
<div class="module cropduster-form nested-inline-form" id="${prefix}-group" data-media-url="${attr(o.mediaUrl)}">
  <input type="hidden" id="id_${prefix}-0-id" name="${prefix}-0-id" value="${attr(o.imageId)}">
  <input type="text" id="id_${prefix}" name="${prefix}" value="${attr(o.image)}"
         class="cropduster-data-field cropduster-text-field"
         data-sizes="${attr(JSON.stringify(o.sizes))}"
         data-preview-url="${attr(o.previewUrl)}"
         data-preview-renderer-url="${attr(o.previewRendererUrl ?? "")}"
         data-preview-srcset="${attr(o.previewSrcset ?? "")}"
         data-preview-w="${attr(String(o.previewW))}"
         data-preview-h="${attr(String(o.previewH))}"
         data-orig-w="${attr(String(o.origW))}"
         data-orig-h="${attr(String(o.origH))}"
         data-upload-to="${attr(o.uploadTo)}">
  ${element}
  <a href="#" class="cropduster-customfield cropduster-upload-form" data-cropduster-url="${attr(o.cropdusterUrl)}">
    <div class="cropduster-button">Upload Image</div>
    <div style="clear:both; height:3px"></div>
  </a>
  <div class="manual_images cropduster-image-group"><div class="thumbs cropduster-images"></div></div>
  <input type="hidden" name="${prefix}-TOTAL_FORMS" id="id_${prefix}-TOTAL_FORMS" value="${o.totalForms}">
  <input type="hidden" name="${prefix}-INITIAL_FORMS" id="id_${prefix}-INITIAL_FORMS" value="${o.initialForms}">
  <input type="hidden" name="${prefix}-MIN_NUM_FORMS" id="id_${prefix}-MIN_NUM_FORMS" value="0">
  <input type="hidden" name="${prefix}-MAX_NUM_FORMS" id="id_${prefix}-MAX_NUM_FORMS" value="1">
  <div class="cropduster-fields">
  <div id="${prefix}-0">
    <span class="delete"><input type="checkbox" name="${prefix}-0-DELETE" id="id_${prefix}-0-DELETE"${o.deleted ? " checked" : ""}></span>
    <div class="form-row field-image">
      <input type="text" name="${prefix}-0-image" id="id_${prefix}-0-image" value="${attr(o.image)}">
    </div>
    <div class="form-row field-thumbs">
      <select multiple name="${prefix}-0-thumbs" id="id_${prefix}-0-thumbs">${o.thumbs
        .map(optionHtml)
        .join("")}</select>
    </div>
    <div class="form-row field-caption">
      <input type="text" name="${prefix}-0-caption" id="id_${prefix}-0-caption" value="">
    </div>
  </div>
  </div>
</div>`;
  return o.withRow
    ? `<div class="form-row field-${prefix.split("-").pop()}">${form}</div>`
    : form;
}

export interface MountedFixture {
  container: HTMLElement;
  root: HTMLElement;
  host: HTMLElement | null;
  dataField: HTMLInputElement;
  anchor: HTMLAnchorElement;
  images: HTMLElement;
  field(suffix: string): HTMLElement | null;
  remove(): void;
}

/** Append one widget's markup to the document and return its parts. */
export function mountFixture(
  options: WidgetFixtureOptions = {},
): MountedFixture {
  const prefix = options.prefix ?? DEFAULTS.prefix;
  const container = document.createElement("div");
  container.innerHTML = widgetHtml(options);
  document.body.appendChild(container);
  const root = container.querySelector<HTMLElement>(".cropduster-form");
  if (!root) {
    throw new Error("fixture has no .cropduster-form");
  }
  return {
    container,
    root,
    host: container.querySelector<HTMLElement>("cropduster-widget"),
    dataField: container.querySelector<HTMLInputElement>(
      ".cropduster-data-field",
    )!,
    anchor: container.querySelector<HTMLAnchorElement>(
      ".cropduster-customfield",
    )!,
    images: container.querySelector<HTMLElement>(".cropduster-images")!,
    field: (suffix: string) =>
      container.querySelector<HTMLElement>(
        `[name="${prefix}-0-${suffix}"], [name="${prefix}-${suffix}"]`,
      ),
    remove: () => container.remove(),
  };
}

function macrotask(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function frame(): Promise<void> {
  return new Promise((resolve) => {
    if (typeof requestAnimationFrame === "function") {
      requestAnimationFrame(() => resolve());
    } else {
      resolve();
    }
  });
}

/**
 * Drain the event loop: queued microtasks, one animation frame, and whatever
 * either of those queued in turn.
 *
 * This waits on the queues rather than on the clock, so it is as fast as the
 * work is. What it is not is a guarantee: one drain only covers work that is
 * already scheduled, and a mount, a fetch round trip or a modal opening take
 * several turns to settle. Assert on those through `waitFor`.
 */
export async function flush(ms = 0): Promise<void> {
  await macrotask(ms);
  await frame();
  await macrotask(ms);
}

export interface WaitForOptions {
  /** Give up after this long. */
  timeout?: number;
  /** How long to sleep between attempts. */
  interval?: number;
  /** What was being waited for, for the timeout message. */
  message?: string;
}

/**
 * Poll until `predicate` returns something truthy, and return it.
 *
 * The unit of a test here is usually "the widget upgraded", "the fetch came
 * back", "the modal is open": states that arrive after an unknown number of
 * event loop turns. Waiting for the state is both faster and reliable; waiting
 * for a duration long enough to cover it is neither.
 *
 * A predicate that throws counts as not-yet, and a timeout reports its error,
 * so `waitFor(() => el.querySelector("img")!.src)` is legal.
 */
export async function waitFor<T>(
  predicate: () => T,
  options: WaitForOptions = {},
): Promise<NonNullable<T>> {
  const { timeout = 2000, interval = 10, message } = options;
  const deadline = Date.now() + timeout;
  let failure: unknown;
  for (;;) {
    await flush();
    try {
      const value = predicate();
      if (value) {
        return value as NonNullable<T>;
      }
      failure = new Error(`predicate returned ${String(value)}`);
    } catch (error) {
      failure = error;
    }
    if (Date.now() >= deadline) {
      const what = message ? `waiting for ${message}` : "waiting";
      throw new Error(
        `timed out after ${timeout}ms ${what}: ${
          failure instanceof Error ? failure.message : String(failure)
        }`,
      );
    }
    await macrotask(interval);
  }
}

/**
 * Whether React has taken a widget's upload button over.
 *
 * Both the template and `UploadButton` render `.cropduster-button` into the
 * anchor, so neither the class nor the text tells them apart; the shape does.
 * The template's markup is indented, React's is two element children and
 * nothing else, and mounting empties the anchor in between.
 */
export function isWidgetMounted(scope: ParentNode): boolean {
  const anchor = scope.querySelector(".cropduster-customfield");
  const first = anchor?.firstChild;
  return (
    anchor?.childNodes.length === 2 &&
    first instanceof Element &&
    first.classList.contains("cropduster-button")
  );
}

/** Wait until React owns the widget in `scope` and its handlers are attached. */
export async function waitForWidget(
  scope: ParentNode,
  options: WaitForOptions = {},
): Promise<void> {
  await waitFor(() => isWidgetMounted(scope), {
    message: "the widget to mount",
    ...options,
  });
  // The click handler is attached in an effect, which React runs after the
  // commit the wait above observed.
  await flush();
}

/** Append a widget's markup and wait for it to mount. */
/** Query the widget's summary card, which renders in `images`' shadow root. */
export function cardQuery<T extends Element = Element>(
  images: HTMLElement,
  selector: string,
): T | null {
  return (images.shadowRoot?.querySelector(selector) as T | null) ?? null;
}

export function cardQueryAll(images: HTMLElement, selector: string): Element[] {
  return [...(images.shadowRoot?.querySelectorAll(selector) ?? [])];
}

export async function mountWidget(
  options: WidgetFixtureOptions = {},
): Promise<MountedFixture> {
  const fixture = mountFixture(options);
  await waitForWidget(fixture.container);
  return fixture;
}

/**
 * Resize the jsdom viewport, and return the undo.
 *
 * jsdom's `innerWidth`/`innerHeight` are fixed at 1024x768, which is large
 * enough for the modal; anything testing the other side of that choice has to
 * say so.
 */
export function setViewport(width: number, height: number): () => void {
  const previous = {
    innerWidth: window.innerWidth,
    innerHeight: window.innerHeight,
  };
  const define = (size: { innerWidth: number; innerHeight: number }) => {
    Object.defineProperty(window, "innerWidth", {
      configurable: true,
      value: size.innerWidth,
    });
    Object.defineProperty(window, "innerHeight", {
      configurable: true,
      value: size.innerHeight,
    });
  };
  define({ innerWidth: width, innerHeight: height });
  return () => define(previous);
}

/**
 * Empty the document and let the widgets finish tearing down.
 *
 * Teardown is deferred by a timer (so that a widget being dragged survives the
 * detach), which would otherwise fire after the test environment is gone.
 */
export async function cleanupDocument(): Promise<void> {
  document.body.innerHTML = "";
  await flush(5);
}
