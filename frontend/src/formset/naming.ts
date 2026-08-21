/**
 * Django formset names used by the widget.
 *
 * django-nested-admin can rename or move a row, so callers read the current
 * prefix from the DOM rather than caching it.
 */

/** The input the widget derives its prefix from. */
export const DATA_FIELD_SELECTOR = ".cropduster-data-field";

/** Management form fields on a formset prefix. */
export type ManagementKey =
  "TOTAL_FORMS" | "INITIAL_FORMS" | "MIN_NUM_FORMS" | "MAX_NUM_FORMS";

export interface NamedElementLike {
  getAttribute(name: string): string | null;
}

export interface PrefixRootLike {
  querySelector(selectors: string): NamedElementLike | null;
}

/**
 * Return true for Django's `__prefix__` rows and the `-empty` forms used by
 * grappelli and django-nested-admin.
 */
export function isTemplatePrefix(prefix: string | null | undefined): boolean {
  if (!prefix) {
    return false;
  }
  return (
    prefix.includes("__prefix__") ||
    prefix.endsWith("-empty") ||
    prefix.includes("-empty-")
  );
}

/**
 * Read the current formset prefix from the widget's data field.
 */
export function derivePrefix(root: PrefixRootLike): string | null {
  const field = root.querySelector(DATA_FIELD_SELECTOR);
  if (!field) {
    return null;
  }
  return field.getAttribute("name") || null;
}

export function joinField(
  prefix: string,
  index: number | string,
  suffix: string,
): string {
  return `${prefix}-${index}-${suffix}`;
}

export function managementField(prefix: string, key: ManagementKey): string {
  return `${prefix}-${key}`;
}

export function fieldId(name: string): string {
  return `id_${name}`;
}
