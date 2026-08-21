/**
 * Load the 4.x dialog JavaScript from `v4.15.0` into jsdom and expose its crop
 * calculations.
 *
 * The tagged source is not modified. It is read as a string and changed in
 * memory in two places:
 *
 *   1. Both `$(document).ready(...)` boot calls are turned into calls on a
 *      no-op function, so the callbacks are constructed but never invoked.
 *      Nothing else in the file is touched: the callbacks' text is preserved
 *      verbatim, only the receiver of the call changes.
 *   2. An assignment to `window.__cropdusterTestExports` is inserted just
 *      before the closing `}(django.jQuery));` of the file's single IIFE, which
 *      is the only way to reach the IIFE-scoped `CropBoxClass`, `calcMinSize`
 *      and `syncSizeForm`.
 *
 * Small Jcrop and DOM stubs supply the values read by those functions.
 */

import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import jqueryFactory from "jquery";
import { JSDOM } from "jsdom";

/* global process */

const HERE = dirname(fileURLToPath(import.meta.url));

export const REPO_ROOT = resolve(HERE, "..", "..", "..");
export const GOLDEN_DIR = resolve(REPO_ROOT, "frontend", "tests", "golden");

/**
 * The git ref the legacy dialog is read from.
 *
 * Version 5.0 removed `upload.js` with the old dialog, so the vectors must be
 * extracted from the final 4.x release rather than the working tree. The git
 * read also keeps the `generatedFrom` label reproducible: it contains version
 * 4.15.0 and the SHA-256 digest of that tag's `upload.js`. The `4.x`
 * maintenance branch contains the same file and can be used as an override.
 */
const LEGACY_REF = process.env.CROPDUSTER_LEGACY_REF ?? "v4.15.0";

const UPLOAD_JS = "cropduster/static/cropduster/js/upload.js";
const CLASS_JS = "cropduster/static/cropduster/js/jquery.class.js";
const VERSION_PY = "cropduster/__init__.py";

/** Read one legacy file from the configured git ref. */
function readLegacyFile(path) {
  try {
    return execFileSync("git", ["show", `${LEGACY_REF}:${path}`], {
      cwd: REPO_ROOT,
      maxBuffer: 32 * 1024 * 1024,
    });
  } catch {
    throw new Error(
      `could not read ${path} from ${LEGACY_REF}. The v4.15.0 tag is where ` +
        `the legacy dialog lives; set CROPDUSTER_LEGACY_REF to name another.`,
    );
  }
}

const READY_CALL = "$(document).ready(";
const NEUTRALIZED_READY_CALL = "(function(neverRunReadyCallback){})(";
const IIFE_TAIL = "}(django.jQuery));";

const EXPORT_HOOK = `
    window.__cropdusterTestExports = {
        CropBoxClass: CropBoxClass,
        calcMinSize: calcMinSize,
        syncSizeForm: syncSizeForm,
        setFormData: setFormData,
        getFormData: window.getFormData,
        registerStandaloneSizeHandlers: registerStandaloneSizeHandlers
    };
`;

export function readLegacySource() {
  const bytes = readLegacyFile(UPLOAD_JS);
  const sha256 = createHash("sha256").update(bytes).digest("hex");
  const version = readLegacyFile(VERSION_PY)
    .toString("utf8")
    .match(/__version__\s*=\s*['"]([^'"]+)['"]/)[1];
  return { source: bytes.toString("utf8"), sha256, version };
}

export function generatedFromLabel() {
  const { sha256, version } = readLegacySource();
  return `cropduster ${version} upload.js sha256:${sha256}`;
}

function patchUploadSource(source) {
  const parts = source.split(READY_CALL);
  if (parts.length !== 3) {
    throw new Error(
      `expected 2 ${READY_CALL} boot calls, found ${parts.length - 1}`,
    );
  }
  let patched = parts.join(NEUTRALIZED_READY_CALL);

  const tailIndex = patched.lastIndexOf(IIFE_TAIL);
  if (tailIndex === -1) {
    throw new Error(`could not find the IIFE close "${IIFE_TAIL}"`);
  }
  patched =
    patched.slice(0, tailIndex) + EXPORT_HOOK + patched.slice(tailIndex);

  if (patched.includes(".ready(")) {
    throw new Error("a $(document).ready() boot call survived the splice");
  }
  return patched;
}

/**
 * Load jQuery, jquery.class.js, and the modified upload.js into jsdom.
 *
 * @param {string} html markup for the DOM the captured code paths read/write
 */
export function createLegacyEnv(html) {
  const dom = new JSDOM(
    `<!doctype html><html><body class="cropduster">${html}</body></html>`,
    {
      runScripts: "outside-only",
      url: "https://example.test/cropduster/upload/",
    },
  );
  const { window } = dom;

  const $ = jqueryFactory(window);
  window.jQuery = $;
  window.$ = $;
  window.django = { jQuery: $ };

  // `this.Class = function(){}` at the top level of the IIFE in jquery.class.js
  // needs `this` to be the jsdom window, which is what window.eval gives it.
  window.eval(readLegacyFile(CLASS_JS).toString("utf8"));
  if (typeof window.Class !== "function") {
    throw new Error("jquery.class.js did not define a global Class");
  }

  window.eval(patchUploadSource(readLegacySource().source));
  const legacy = window.__cropdusterTestExports;
  if (!legacy || typeof legacy.CropBoxClass !== "function") {
    throw new Error("upload.js exports were not spliced in");
  }

  return { dom, window, $, legacy };
}

/**
 * Implement the three Jcrop operations used by `setCropOptions()` and
 * `updateCoordinates()`.
 */
export function installJcropStub($) {
  const calls = [];
  $.fn.Jcrop = function (options, callback) {
    const api = {
      _options: $.extend({}, options),
      getOptions() {
        return this._options;
      },
      setOptions(newOptions) {
        this._options = $.extend({}, this._options, newOptions);
        calls.push($.extend({}, newOptions));
      },
      destroy() {},
    };
    calls.push($.extend({}, options));
    if (typeof callback === "function") {
      callback.call(api);
    }
    return this;
  };
  return {
    calls,
    reset() {
      calls.length = 0;
    },
    last() {
      return calls[calls.length - 1];
    },
  };
}

/** jsdom images report naturalWidth/naturalHeight 0; the dialog reads both. */
export function setNaturalSize(element, width, height) {
  Object.defineProperty(element, "naturalWidth", {
    configurable: true,
    get: () => width,
  });
  Object.defineProperty(element, "naturalHeight", {
    configurable: true,
    get: () => height,
  });
}

/** JSON has no Infinity; getAspectRatioExtent can return it for `max`. */
export function jsonNumber(value) {
  if (value === Infinity) return "Infinity";
  if (value === -Infinity) return "-Infinity";
  if (typeof value === "number" && Number.isNaN(value)) return "NaN";
  return value;
}

/**
 * Pretty top-level object with one array element per line: large golden files
 * stay diffable without the size blowup of a fully indented dump.
 */
export function writeGoldenJson(path, object, lineArrayKeys) {
  const lines = ["{"];
  const keys = Object.keys(object);
  keys.forEach((key, index) => {
    const comma = index === keys.length - 1 ? "" : ",";
    if (lineArrayKeys.includes(key)) {
      const items = object[key];
      if (!items.length) {
        lines.push(`  ${JSON.stringify(key)}: []${comma}`);
        return;
      }
      lines.push(`  ${JSON.stringify(key)}: [`);
      items.forEach((item, i) => {
        lines.push(
          `    ${JSON.stringify(item)}${i === items.length - 1 ? "" : ","}`,
        );
      });
      lines.push(`  ]${comma}`);
    } else {
      lines.push(
        `  ${JSON.stringify(key)}: ${JSON.stringify(object[key])}${comma}`,
      );
    }
  });
  lines.push("}");
  writeFileSync(path, lines.join("\n") + "\n", "utf8");
}
