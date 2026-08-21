/**
 * Client for `/cropduster/api/v1/`.
 *
 * The state, upload, and crop endpoints return the object produced by
 * `build_payload()`. Failures use non-2xx responses with an `error` object.
 * CSRF tokens are read from widget configuration, then the cookie, then a
 * `csrfmiddlewaretoken` input.
 */

import type { DialogConfig } from "../state/dialogConfig";
import type { CropDusterPayload } from "../formset/legacyPayload";

/** The cookie Django writes the CSRF token to (`CSRF_COOKIE_NAME`). */
const CSRF_COOKIE = "csrftoken";

/** The hidden input `{% csrf_token %}` renders. */
const CSRF_INPUT = "input[name=csrfmiddlewaretoken]";

/** What the dialog says when the server does not say anything usable. */
export const UNKNOWN_ERROR = "An unknown error occurred.";

/** A crop was asked for from a source other than the image being cropped. */
export const PER_SIZE_SOURCE_UNSUPPORTED = "per_size_source_unsupported";

/** The project routed 4.x's views without including the API. */
export const API_UNAVAILABLE = "api_unavailable";

export interface ApiErrorBody {
  code?: unknown;
  message?: unknown;
  field?: unknown;
  details?: unknown;
}

/**
 * A failure the dialog shows to the editor.
 *
 * `code` is the stable half and is what anything branching on a failure reads;
 * `message` is editor-facing prose. Both come from the error envelope, or are
 * synthesised for a response that included none (a proxy, a network error).
 */
export class DialogError extends Error {
  readonly status: number;
  readonly code: string;
  readonly field: string | null;
  readonly details: unknown;

  constructor(
    message: string,
    options: {
      status?: number;
      code?: string;
      field?: string | null;
      details?: unknown;
    } = {},
  ) {
    super(message);
    this.name = "DialogError";
    this.status = options.status ?? 0;
    this.code = options.code ?? "error";
    this.field = options.field ?? null;
    this.details = options.details ?? null;
  }
}

/**
 * Whether a failure reports the reserved per-size source code.
 *
 * `source` round-trips through every endpoint from day one and naming anything
 * but the image being cropped is answered 501, not 500: it is a feature that
 * has not shipped rather than a bug, and the dialog says so.
 */
export function isSourceUnsupported(error: unknown): boolean {
  return (
    error instanceof DialogError && error.code === PER_SIZE_SOURCE_UNSUPPORTED
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function str(value: unknown): string | null {
  return typeof value === "string" && value ? value : null;
}

/** The token, from the config, the cookie, or the page, in that order. */
export function csrfToken(
  config: Pick<DialogConfig, "csrfToken">,
  doc: Document = document,
): string | null {
  if (config.csrfToken) {
    return config.csrfToken;
  }
  for (const part of doc.cookie ? doc.cookie.split(";") : []) {
    const [name, ...rest] = part.trim().split("=");
    if (name === CSRF_COOKIE) {
      return decodeURIComponent(rest.join("=")) || null;
    }
  }
  const input = doc.querySelector<HTMLInputElement>(CSRF_INPUT);
  return input?.value || null;
}

/**
 * The API's base path, or null when the project has none.
 *
 * cropduster 4.x's three views can be routed without `cropduster.urls`, in
 * which case there is no `api/` prefix to name and the dialog has nothing to
 * talk to; that is a configuration error, reported as one.
 */
export function apiBase(config: DialogConfig): string | null {
  return config.urls.api;
}

function endpoint(config: DialogConfig, path: string): string {
  const base = apiBase(config);
  if (!base) {
    throw new DialogError(
      "The cropduster JSON API is not routed; include cropduster.urls.",
      { code: API_UNAVAILABLE },
    );
  }
  return `${base}${path}`;
}

/** The envelope, or a synthesised error for a response that included none. */
function errorFrom(response: Response, data: unknown): DialogError {
  const envelope =
    isRecord(data) && isRecord(data.error)
      ? (data.error as ApiErrorBody)
      : null;
  if (!envelope) {
    return new DialogError(UNKNOWN_ERROR, {
      status: response.status,
      code: "server_error",
    });
  }
  return new DialogError(str(envelope.message) ?? UNKNOWN_ERROR, {
    status: response.status,
    code: str(envelope.code) ?? "error",
    field: str(envelope.field),
    details: envelope.details ?? null,
  });
}

async function request(
  url: string,
  init: RequestInit,
): Promise<CropDusterPayload> {
  let response: Response;
  try {
    response = await fetch(url, { credentials: "same-origin", ...init });
  } catch {
    throw new DialogError(UNKNOWN_ERROR, { code: "network_error" });
  }

  let data: unknown;
  try {
    data = await response.json();
  } catch {
    data = null;
  }

  if (!response.ok) {
    throw errorFrom(response, data);
  }
  if (!isRecord(data)) {
    throw new DialogError(UNKNOWN_ERROR, {
      status: response.status,
      code: "server_error",
    });
  }
  return data as unknown as CropDusterPayload;
}

function headers(config: DialogConfig, extra: HeadersInit = {}): HeadersInit {
  const token = csrfToken(config);
  return { ...(token ? { "X-CSRFToken": token } : {}), ...extra };
}

/**
 * The `target` a request names, using the API's field names.
 *
 * `cropduster.api.schema.parse_target` reads `content_type`, `object_id` and
 * `field_name`; the config includes the same three under the client's own
 * names. With a named target the server answers from the field's declaration
 * (the size set and the upload directory come from the model, and sizes the
 * client named are checked against it) rather than trusting what was sent. A dialog with no target (the page dialog) is answered as 4.x
 * always answered it.
 */
function targetParam(config: DialogConfig): Record<string, unknown> | null {
  const target = config.target;
  if (!target) {
    return null;
  }
  return {
    content_type: target.model,
    object_id: target.objectId,
    field_name: target.fieldName,
  };
}

export type StateParams = Record<string, string | null | undefined>;

/**
 * `POST state/`: load the dimensions and crops missing from the formset.
 *
 * The modal is the caller: it knows the image, the crops and the sizes from the
 * formset it is opening over, but not the original's dimensions or the boxes
 * those crops were made with, which is one round trip's worth of state. A
 * dialog with nothing on the page yet makes no call at all.
 */
export async function getState(
  config: DialogConfig,
  params: StateParams,
): Promise<CropDusterPayload> {
  const target = targetParam(config);
  const body = new URLSearchParams();
  for (const [name, value] of Object.entries(params)) {
    if (value !== null && value !== undefined && value !== "") {
      body.append(name, value);
    }
  }
  if (target) {
    body.set("target", JSON.stringify(target));
  }
  return request(endpoint(config, "state/"), {
    method: "POST",
    headers: headers(config),
    body,
  });
}

export interface UploadOptions {
  /**
   * Validate the upload against one size rather than all of them, which is
   * what lets a crop be re-uploaded from a source no other size could satisfy.
   */
  forSize?: string | null;
}

/** `POST upload/`: store an image and answer with the state it produced. */
export async function upload(
  config: DialogConfig,
  body: FormData,
  options: UploadOptions = {},
): Promise<CropDusterPayload> {
  if (options.forSize) {
    body.set("for_size", options.forSize);
  }
  const target = targetParam(config);
  if (target) {
    body.set("target", JSON.stringify(target));
  }
  return request(endpoint(config, "upload/"), {
    method: "POST",
    headers: headers(config),
    body,
  });
}

/** `POST crop/`: render the crops the body asks for. */
export async function crop(
  config: DialogConfig,
  body: unknown,
): Promise<CropDusterPayload> {
  const target = targetParam(config);
  const withTarget = target && isRecord(body) ? { ...body, target } : body;
  return request(endpoint(config, "crop/"), {
    method: "POST",
    headers: headers(config, { "Content-Type": "application/json" }),
    body: JSON.stringify(withTarget),
  });
}
