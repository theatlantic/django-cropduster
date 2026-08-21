/** Editor-facing presentation of stored image names. */

/**
 * The name an editor knows the file by.
 *
 * `store_upload` renames every upload to `<basename>/original.<ext>`, an
 * implementation detail left over from rendition generation; present the
 * directory's name with the file's extension instead.
 */
export function displayFilename(name: string): string {
  const segments = name.split("/").filter(Boolean);
  const base = segments[segments.length - 1] ?? "";
  const dot = base.lastIndexOf(".");
  const stem = dot > 0 ? base.slice(0, dot) : base;
  const parent = segments[segments.length - 2];
  if (stem === "original" && parent) {
    return `${parent}${dot > 0 ? base.slice(dot) : ""}`;
  }
  return base;
}

export function middleTruncate(value: string, max = 24): string {
  if (value.length <= max) {
    return value;
  }
  const keep = max - 1;
  const head = Math.ceil(keep / 2);
  return `${value.slice(0, head)}…${value.slice(value.length - (keep - head))}`;
}

/** The display name for a filename's format, or null without an extension. */
export function formatOf(filename: string): string | null {
  const dot = filename.lastIndexOf(".");
  if (dot <= 0) {
    return null;
  }
  const ext = filename.slice(dot + 1).toUpperCase();
  return ext === "JPG" ? "JPEG" : ext;
}

/** The "1440 × 1800 · JPEG" line shown under a filename. */
export function imageDetail(
  width: number | null | undefined,
  height: number | null | undefined,
  filename: string,
): string {
  const dimensions = width && height ? `${width} × ${height}` : null;
  return [dimensions, formatOf(filename)].filter(Boolean).join(" · ");
}

/**
 * 4.x's guard on a stored file name: path, basename, optional extension.
 * A name without a directory separator does not match.
 */
const STORED_IMAGE_PATH = /^(.*)(\/(?:[^/](?!\.[^./?]+))*[^./?])(\.[^./?]+)?$/;

export function isStoredImagePath(name: string): boolean {
  return Boolean(name) && STORED_IMAGE_PATH.test(name);
}
