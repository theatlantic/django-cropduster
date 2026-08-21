/**
 * Own one FormsetBridge and React root.
 *
 * The root remains on `<cropduster-widget>` while the visible button and
 * thumbnails render into server-provided containers, preserving the DOM shape
 * used by downstream stylesheets.
 */

import { createElement } from "react";
import { createRoot } from "react-dom/client";
import type { Root } from "react-dom/client";

import { SELECTORS } from "../constants/classNames";
import { FormsetBridge } from "../formset/FormsetBridge";
import type { WidgetState } from "../formset/FormsetBridge";
import { Widget } from "../components/widget/Widget";
import { readData } from "./jquery";
import { registry } from "./registry";
import type { WidgetHandle } from "./registry";
import type { WidgetConfig } from "./config";

/**
 * The server-rendered containers React portals into.
 *
 * Resolved once, at mount. The one thing on the page that replaces DOM inside
 * a widget wholesale is django-autosave's revert, and it recreates only the
 * inputs (from name/value pairs), leaving these two containers in place.
 */
export interface WidgetSlots {
  /** `a.cropduster-customfield`, which holds the upload button. */
  button: HTMLElement | null;
  /** `div.thumbs.cropduster-images`, which hosts the summary card's shadow root. */
  images: HTMLElement | null;
  /**
   * The container inside `images`' shadow root the card renders into, so
   * admin themes cannot restyle it; pages customize through `::part()`.
   */
  cards: HTMLElement | null;
}

export function resolveSlots(root: HTMLElement): WidgetSlots {
  return {
    button: root.querySelector<HTMLElement>(SELECTORS.customField),
    images: root.querySelector<HTMLElement>(SELECTORS.images),
    cards: null,
  };
}

/** The card container in `images`' shadow root, made (once) on mount. */
function resolveCardContainer(images: HTMLElement | null): HTMLElement | null {
  if (!images || typeof images.attachShadow !== "function") {
    return null;
  }
  const shadow = images.shadowRoot ?? images.attachShadow({ mode: "open" });
  const existing = shadow.querySelector<HTMLElement>(".cropduster-card-root");
  if (existing) {
    return existing;
  }
  const container = images.ownerDocument.createElement("div");
  container.className = "cropduster-card-root";
  shadow.appendChild(container);
  return container;
}

/**
 * Whether both containers the template provides are in the DOM.
 *
 * They are the last two children of the widget's wrapper, and the element
 * whose insertion triggers a mount is the third; so on a server-rendered page
 * the parser has not reached them yet when this element connects.
 */
export function hasSlots(root: HTMLElement): boolean {
  const slots = resolveSlots(root);
  return Boolean(slots.button && slots.images);
}

export class WidgetInstance implements WidgetHandle {
  readonly root: HTMLElement;
  readonly host: HTMLElement;
  readonly config: WidgetConfig;
  readonly bridge: FormsetBridge;
  readonly slots: WidgetSlots;

  #reactRoot: Root | null;

  constructor(root: HTMLElement, host: HTMLElement, config: WidgetConfig) {
    this.root = root;
    this.host = host;
    this.config = config;
    this.bridge = new FormsetBridge(root, {
      dispatchInputEvents: config.dispatchInputEvents,
    });
    this.slots = resolveSlots(root);

    // The template includes the button markup so the widget looks right
    // before the bundle runs; React renders the same markup and manages it
    // afterward.
    this.slots.button?.replaceChildren();
    this.slots.images?.replaceChildren();
    this.slots.cards = resolveCardContainer(this.slots.images);

    this.#reactRoot = createRoot(host);
    this.#reactRoot.render(createElement(Widget, { instance: this }));
  }

  /** The media URL this widget was rendered with. */
  get mediaUrl(): string {
    const fromDom = readData(this.root, "mediaUrl");
    return typeof fromDom === "string" && fromDom
      ? fromDom
      : this.config.mediaUrl;
  }

  subscribe = (callback: () => void): (() => void) =>
    this.bridge.subscribe(callback);

  getState = (): WidgetState => this.bridge.getSnapshot();

  refresh() {
    this.bridge.refresh();
  }

  destroy() {
    const reactRoot = this.#reactRoot;
    this.#reactRoot = null;
    reactRoot?.unmount();
    this.bridge.destroy();
    registry.remove(this);
  }
}
