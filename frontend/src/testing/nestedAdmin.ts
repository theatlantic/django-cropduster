/**
 * django-nested-admin row operations used by the widget integration tests.
 *
 * These helpers retain its add, gap-filling, and cross-group rename regexes,
 * including the non-global replacement and negative lookahead. They also use
 * the same attribute selector list, which omits `<cropduster-widget>`.
 */

/** `utils.js:20-33`, with jQuery's `:input` expanded. */
const SELECTOR = [
  "input",
  "textarea",
  "select",
  "button",
  "span",
  "table",
  "iframe",
  "label",
  "a",
  "ul",
  "p",
  "img",
  ".djn-group",
  ".djn-inline-form",
  ".cropduster-form",
  ".dal-forward-conf",
].join(",");

/** `utils.js:41-49`. */
const ATTRIBUTES = [
  "id",
  "name",
  "for",
  "href",
  "class",
  "onclick",
  "data-inline-formset",
];

/** `regexquote.js`. */
export function regexQuote(str: string): string {
  return str.replace(/[.?*+^$[\]\\(){}|-]/g, "\\$&");
}

/**
 * Rewrite the six renameable attributes on `el` and its matching descendants.
 *
 * `$elem.find(selector).addBack()` includes the element itself, which is how a
 * `.cropduster-form` wrapper gets its own `id` moved.
 */
export function updateFormAttributes(
  el: Element,
  search: RegExp,
  replace: string,
): void {
  const targets = [...el.querySelectorAll(SELECTOR)];
  if (el.matches(SELECTOR)) {
    targets.push(el);
  }
  for (const target of targets) {
    for (const attribute of ATTRIBUTES) {
      const value = target.getAttribute(attribute);
      if (value) {
        target.setAttribute(attribute, value.replace(search, replace));
      }
    }
  }
}

/**
 * `add()`: clone the empty-form template and give the clone an index.
 *
 * The template's container ids carry `-empty` and its field names carry
 * `__prefix__`; one regex covers both.
 */
export function cloneTemplateRow(
  template: Element,
  prefix: string,
  index: number,
): HTMLElement {
  const row = template.cloneNode(true) as HTMLElement;
  const id = row.getAttribute("id");
  if (id) {
    row.setAttribute("id", id.replace(/-empty.*?$/, `-${index}`));
  }
  updateFormAttributes(
    row,
    new RegExp(
      `([#_]id_|[#]|^id_|"|^)${regexQuote(prefix)}\\-(?:__prefix__|empty)\\-`,
      "g",
    ),
    `$1${prefix}-${index}-`,
  );
  return row;
}

/**
 * `_fillGap()` / `spliceInto()`: renumber one row of a group.
 *
 * Retain nested-admin's non-global, lookahead-guarded regex so the test sees
 * the same partial-match behavior.
 */
export function renameRow(
  row: Element,
  prefix: string,
  oldIndex: number | string,
  newIndex: number | string,
): void {
  row.setAttribute("id", `${prefix}-${newIndex}`);
  updateFormAttributes(
    row,
    new RegExp(`([\\#_]|^)${regexQuote(`${prefix}-${oldIndex}`)}(?!\\-\\d)`),
    `$1${prefix}-${newIndex}`,
  );
}
