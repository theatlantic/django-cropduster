/**
 * Load recorded 4.15 requests and responses for frontend conversion tests.
 * `{Y}/{m}` and `{DIR}` replace date- and run-specific path segments.
 */

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import type {
  LegacyCompletePayload,
  LegacyUploadResponse,
} from "../formset/legacyPayload";

// Avoid `new URL(..., import.meta.url)`, which Vite treats as an asset import
// outside the frontend root.
const FIXTURE_DIR = join(
  dirname(fileURLToPath(import.meta.url)),
  "..",
  "..",
  "..",
  "tests",
  "data",
  "legacy_wire",
);

export interface RecordedRequest {
  method: string;
  path: string;
  post: Record<string, string>;
  files: Record<string, string>;
}

export interface RecordedFixture<T> {
  request: RecordedRequest;
  response: T;
  description: string;
}

function load(name: string): {
  _meta: Record<string, unknown>;
  response: unknown;
} {
  const raw = readFileSync(join(FIXTURE_DIR, `${name}.json`), "utf8");
  return JSON.parse(raw) as {
    _meta: Record<string, unknown>;
    response: unknown;
  };
}

export function legacyFixture<T>(name: string): RecordedFixture<T> {
  const raw = load(name);
  const meta = raw._meta as {
    request: RecordedRequest;
    description: string;
  };
  return {
    request: meta.request,
    response: raw.response as T,
    description: meta.description,
  };
}

export function uploadFixture(name: string) {
  return legacyFixture<LegacyUploadResponse>(name);
}

export function cropFixture(name: string) {
  return legacyFixture<LegacyCompletePayload>(name);
}

/** Convert a form or multipart body to the object stored in a recording. */
export function bodyToObject(
  body: URLSearchParams | FormData,
): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [key, value] of body.entries()) {
    if (typeof value === "string") {
      out[key] = value;
    }
  }
  return out;
}
