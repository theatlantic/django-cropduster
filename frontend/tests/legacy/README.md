# Legacy dialog vector extraction

These scripts run the Cropduster 4.x crop calculations in jsdom and record
their results for the 5.0 TypeScript rewrite. They read
`cropduster/static/cropduster/js/upload.js` from the `v4.15.0` tag with
`git show`; set `CROPDUSTER_LEGACY_REF` to use another ref.

The loader does not check out or modify the tagged source. It reads the
JavaScript as text, suppresses its two `$(document).ready()` calls, and adds an
export immediately before the IIFE closes so the extraction scripts can call
`CropBoxClass`, `calcMinSize`, and `syncSizeForm`.

```
npm run extract:vectors
# or individually, from frontend/:
node tests/legacy/extract-vectors.mjs           # -> tests/golden/default-crop-vectors.json
node tests/legacy/extract-sizeform-vectors.mjs  # -> tests/golden/size-form-vectors.json
```

Both scripts use a fixed iteration order and omit timestamps, so regenerating
against the same ref produces no diff. Before writing, each script compares
hand-computed results with the legacy functions and exits if they differ.
`generatedFrom` stores the SHA-256 digest of the extracted `upload.js`; a
different digest means the vectors came from another ref and must be
regenerated or the ref corrected.

The self-check in `extract-vectors.mjs` includes the geometry checked by
`tests/test_admin.py::test_addform` through Selenium: a
674x800 upload against `Author.HEADSHOT_SIZES` size `main` (220x180) must
produce `{x: 0, y: 125, w: 674, h: 551}`, where 125 is `Math.round(124.5)`.

The extractors read `tests/golden/test-sizes.json` (the test application's
size sets) and `tests/golden/sample-sizes.json` (a larger corpus of example
size sets). They do not generate those files.

`createLegacyEnv()`, `readLegacySource()` and `generatedFromLabel()` read the
three source files from `CROPDUSTER_LEGACY_REF`. Set that environment variable
to regenerate the vectors from another 4.x ref.
