/** Add the embedded dialog and widget-card styles to a shadow root. */

import reactCropCss from "react-image-crop/dist/ReactCrop.css?inline";
import cardCss from "../../../styles/card.css?inline";
import dialogCss from "../../../styles/dialog.css?inline";

export type DialogStyleMode = "page" | "card";

interface ManagedStyles {
  sheets: CSSStyleSheet[];
  elements: HTMLStyleElement[];
}

/** @internal Replacement text supplied by Vite HMR and unit tests. */
export interface DialogStyleSources {
  reactCrop: string;
  dialog: string;
  card: string;
}

/** Styles owned by this module, retained so an HMR update can replace them. */
const managedStyles = new WeakMap<ShadowRoot, ManagedStyles>();

/** Iterable so HMR can refresh roots; hosts remove themselves on teardown. */
const dialogRoots = new Map<ShadowRoot, DialogStyleMode>();

const current: DialogStyleSources = {
  reactCrop: reactCropCss,
  dialog: dialogCss,
  card: cardCss,
};

/**
 * Rewrite `:root` selectors to `:host`.
 *
 * react-image-crop publishes its custom properties on `:root`, which
 * matches nothing inside a shadow tree. Rewriting those selectors to `:host`
 * lets the CSS variables apply inside the shadow root.
 */
export function hostifyRootSelectors(css: string): string {
  return css.replace(/(^|[\s,{}]):root(?![\w-])/g, "$1:host");
}

function withoutManagedSheets(
  root: ShadowRoot,
  sheets: CSSStyleSheet[],
): CSSStyleSheet[] {
  if (!sheets.length) {
    return [...root.adoptedStyleSheets];
  }
  const managed = new Set(sheets);
  return [...root.adoptedStyleSheets].filter((sheet) => !managed.has(sheet));
}

/** Replace the styles through constructable stylesheets when the browser can. */
function replaceConstructedStyles(
  root: ShadowRoot,
  sources: string[],
  previous: ManagedStyles,
): boolean {
  if (typeof CSSStyleSheet !== "function" || !("adoptedStyleSheets" in root)) {
    return false;
  }
  try {
    const sheets =
      previous.sheets.length === sources.length
        ? previous.sheets
        : sources.map(() => new CSSStyleSheet());
    sources.forEach((css, index) => sheets[index]?.replaceSync(css));
    root.adoptedStyleSheets = [
      ...withoutManagedSheets(root, previous.sheets),
      ...sheets,
    ];
    previous.elements.forEach((element) => element.remove());
    managedStyles.set(root, { sheets, elements: [] });
    return true;
  } catch {
    return false;
  }
}

/** Replace the fallback style elements without appending duplicates. */
function replaceStyleElements(
  root: ShadowRoot,
  sources: string[],
  previous: ManagedStyles,
): void {
  if (previous.sheets.length && "adoptedStyleSheets" in root) {
    try {
      root.adoptedStyleSheets = withoutManagedSheets(root, previous.sheets);
    } catch {
      // The fallback elements still override stale managed sheets if removal
      // is unsupported by a partial adoptedStyleSheets implementation.
    }
  }

  const elements = previous.elements.slice(0, sources.length);
  previous.elements
    .slice(sources.length)
    .forEach((element) => element.remove());
  sources.forEach((css, index) => {
    const element =
      elements[index] ?? root.ownerDocument.createElement("style");
    element.textContent = css;
    if (element.getRootNode() !== root) {
      root.appendChild(element);
    }
    elements[index] = element;
  });
  managedStyles.set(root, { sheets: [], elements });
}

/**
 * Prefer constructed stylesheets. Use `<style>` elements in jsdom and browsers
 * without that API. Repeated calls update the styles this module already owns
 * rather than growing the root.
 */
export function adoptStyles(root: ShadowRoot, sources: string[]): void {
  const hostified = sources.map(hostifyRootSelectors);
  const previous = managedStyles.get(root) ?? { sheets: [], elements: [] };
  if (replaceConstructedStyles(root, hostified, previous)) {
    return;
  }
  replaceStyleElements(root, hostified, previous);
}

function sourcesFor(mode: DialogStyleMode): string[] {
  if (mode === "card") {
    return [current.card];
  }
  return [current.reactCrop, current.dialog];
}

/** Adopt the current dialog styles and keep this root live during CSS HMR. */
export function adoptDialogStyles(
  root: ShadowRoot,
  mode: DialogStyleMode,
): void {
  dialogRoots.set(root, mode);
  adoptStyles(root, sourcesFor(mode));
}

/** Stop retaining a root once its host is being removed. */
export function releaseDialogStyles(root: ShadowRoot): void {
  dialogRoots.delete(root);
}

function cssDefault(
  module: Record<string, unknown> | undefined,
  fallback: string,
): string {
  return typeof module?.default === "string" ? module.default : fallback;
}

function refreshDialogRoots(): void {
  for (const [root, mode] of dialogRoots) {
    if (!root.host.isConnected) {
      dialogRoots.delete(root);
      continue;
    }
    adoptStyles(root, sourcesFor(mode));
  }
}

/** @internal Apply replacement CSS text to every connected dialog shadow root. */
export function refreshDialogStyles(
  sources: Partial<DialogStyleSources>,
): void {
  Object.assign(current, sources);
  refreshDialogRoots();
}

if (import.meta.hot) {
  // `?inline` CSS is a JavaScript string module and does not accept its own
  // updates. Accept it here so the change cannot invalidate the React shells
  // and bubble into a full-page reload.
  import.meta.hot.accept(
    [
      "react-image-crop/dist/ReactCrop.css?inline",
      "../../../styles/dialog.css?inline",
      "../../../styles/card.css?inline",
    ],
    ([nextReactCrop, nextDialog, nextCard]) => {
      refreshDialogStyles({
        reactCrop: cssDefault(nextReactCrop, current.reactCrop),
        dialog: cssDefault(nextDialog, current.dialog),
        card: cssDefault(nextCard, current.card),
      });
    },
  );
}
