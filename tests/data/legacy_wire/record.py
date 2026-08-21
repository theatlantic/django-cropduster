#!/usr/bin/env python
"""Record the scenarios used by the Cropduster 4.15 response fixtures.

The JSON files next to this script contain the responses that the 5.0 service
layer (``cropduster.services``) and its view adapters must preserve. The keys,
value types, ``null``/``""``/``0`` distinctions, and HTML in HTTP-200 error
responses are all significant.

What is recorded, and what is not
---------------------------------

The ``response`` half of each fixture was captured from the 4.15.0 code at
:data:`RESPONSE_SOURCE`.

The ``_meta.request`` half is not a recording. The request builders below
(``dialog_config``, ``upload_fields``, ``crop_fields`` and the ``apply_*``
steps) instead build each POST the way the 5.0 dialog builds it.
``dialog_config()`` reads ``#cropduster-app[data-config]``, which 4.15.0's
``upload.html`` does not render. Each fixture stores the 5.0 request beside
the 4.15 response the views must continue to produce for it. Tests assert
both halves, so the request builders and the client cannot diverge without a
test failure.

Re-recording
------------

This script cannot reproduce the fixtures next to it. When run against a
4.x tree, ``dialog_config()`` raises ``KeyError: 'cropduster-app'`` before
the first capture because that tree's ``upload.html`` renders no
``data-config``; when run against a tree with the 5.0 dialog, the captured
responses are the current implementation's, not 4.15.0's. ``main()``
therefore refuses to overwrite an existing fixture without ``--force``.

To recapture a response, replay the request against a 4.15.0 checkout,
building each POST from the release's rendered ``<form>`` rather than from
the builders above, and copy the resulting ``response`` object into the
fixture. Add new scenarios to this script and capture their 4.15 responses
the same way.

Two runs against different directories should produce identical JSON. Each scenario uses a fresh ``MEDIA_ROOT`` and a flushed database, and
``normalize()`` replaces the remaining values that vary between runs.

Using the fixtures from a test
------------------------------

Import ``normalize`` from this module and apply it to the *raw response body
text* before comparing::

    from tests.data.legacy_wire.record import normalize

    fixture = json.load(open(".../upload_author_headshot.json"))
    actual = json.loads(normalize(response.content.decode("utf-8")))
    assert actual == fixture["response"]

The recorded request in ``_meta.request`` passed through the same
transform, so live POST data can be compared against it after the same
``normalize()`` call, or matched against the ``{DIR}``-style placeholders.
"""

import argparse
import io
import json as stdlib_json
import os
import re
import shutil
import sys
import tempfile


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------

#: Source of the ``response`` object in every fixture.
#:
#: These values are fixed rather than read from the running tree because the
#: tree this script runs against is not the one that produced the 4.15
#: responses.
RESPONSE_SOURCE = {
    "cropduster_version": "4.15.0",
    "git_rev": "32167545c4ff386e2bfcca805fe9c78ffcb778cb",
    "git_ref": "4.x",
    "django_version": "5.2.17",
    "settings_module": "tests.settings",
}

#: Source of ``_meta.request``, which was not recorded from 4.15.0.
REQUEST_SOURCE = (
    "Not recorded from 4.15.0: the 5.0 dialog's own POST, built by "
    "tests/data/legacy_wire/record.py from the dialog config the client reads, "
    "and frozen beside the response it was answered with.")


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------
#
# Every rule is a plain regex over the raw JSON *text* (not the parsed object),
# so that the exact same string transform can be applied to a 5.0 response
# before comparing it against a fixture.

#: ``.../2026/08/...`` -> ``.../{Y}/{m}/...``.  Date-based ``upload_to``
#: patterns ("author/headshots/%Y/%m") expand at request time.
DATE_PATH_RE = re.compile(r"(?<=/)(?:19|20)\d{2}/\d{2}(?=/)")

#: The per-upload directory cropduster derives from the uploaded filename
#: (``get_upload_foldername``): the last path segment before an image basename.
#: It is the uploaded file's stem plus a ``-N`` suffix when the directory
#: already exists ("img", "img-1", "img-2"). The whole segment is replaced
#: with ``{DIR}`` so that existing suffixes do not affect the fixture.
IMAGE_DIR_RE = re.compile(
    r'(?<=/)[^/"\\]+(?=/[A-Za-z0-9_@.\-]+\.(?:jpe?g|png|gif|tiff?|webp)\b)')

#: Cache-busting mtime query parameters appended to generated media URLs.
MTIME_QS_RE = re.compile(r"(?<=[?&])(?:_|t|v|ts|mtime)=\d{9,}")

#: The ``id`` Django >= 5.2 renders on an ``<ul class="errorlist">`` built with
#: a ``field_id``.  The optional backslashes match the escaped quotes the HTML
#: has once it is inside a JSON string.
ERROR_ID_RE = re.compile(r' id=\\?"id_[^"\\]*_error\\?"')

NORMALIZE_RULES = [
    {
        "name": "DATE",
        "pattern": DATE_PATH_RE.pattern,
        "replacement": "{Y}/{m}",
        "why": (
            "upload_to values contain strftime codes (%Y/%m); the expanded "
            "year/month depends on the recording date."),
    },
    {
        "name": "DIR",
        "pattern": IMAGE_DIR_RE.pattern,
        "replacement": "{DIR}",
        "why": (
            "get_upload_foldername() appends a -N suffix when a directory of "
            "that name already exists, so the slug depends on storage state."),
    },
    {
        "name": "MTIME",
        "pattern": MTIME_QS_RE.pattern,
        "replacement": "{MTIME}",
        "why": "mtime-based cache-busting query params on generated media URLs.",
    },
    {
        "name": "ERROR_ID",
        "pattern": ERROR_ID_RE.pattern,
        "replacement": "",
        "why": (
            "Django 5.2 added ErrorList(field_id=...), which renders "
            "id=\"id_<auto_id>_error\" on the <ul class=\"errorlist\"> of a "
            "field error; earlier versions render no id at all."),
    },
]

#: Applied in this order.
_SUBSTITUTIONS = [
    (DATE_PATH_RE, "{Y}/{m}"),
    (IMAGE_DIR_RE, "{DIR}"),
    (MTIME_QS_RE, "{MTIME}"),
    (ERROR_ID_RE, ""),
]


def normalize(json_text):
    """Replace nondeterministic substrings in a raw JSON response body.

    md5 digests are *not* normalized: the inputs are fixed files checked into
    tests/data, so every digest in these fixtures is reproducible.
    """
    for pattern, replacement in _SUBSTITUTIONS:
        json_text = pattern.sub(replacement, json_text)
    return json_text


def normalize_obj(obj):
    """Apply :func:`normalize` to every string in a JSON-able structure."""
    if isinstance(obj, str):
        return normalize(obj)
    if isinstance(obj, dict):
        return {k: normalize_obj(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [normalize_obj(v) for v in obj]
    return obj


# ---------------------------------------------------------------------------
# Django bootstrap
# ---------------------------------------------------------------------------

DATA_DIR = os.path.dirname(os.path.abspath(__file__))
TEST_IMG_DIR = os.path.dirname(DATA_DIR)


def bootstrap_django():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tests.settings")
    import django

    django.setup()
    from django.test.utils import setup_databases, setup_test_environment

    setup_test_environment()
    setup_databases(verbosity=0, interactive=False)


# ---------------------------------------------------------------------------
# A small re-implementation of the pieces of the dialog that build the POSTs
# ---------------------------------------------------------------------------
#
# The dialog builds both POSTs from ``#cropduster-app[data-config]``. These
# helpers use the same state because omitted fields and empty values are part
# of the request format. ``tests/test_legacy_wire_format.py`` compares each
# POST with the request stored beside its 4.15 response.


def dialog_config(html):
    """Parse the dialog config from ``#cropduster-app[data-config]``."""
    import lxml.html

    tree = lxml.html.fromstring(html)
    return stdlib_json.loads(
        tree.get_element_by_id("cropduster-app").get("data-config"))


def _text(value, default=""):
    """A value as the client serializes it: never null, always a string."""
    if value is None or value == "":
        return default
    return "%s" % value


def upload_fields(config, dumps):
    """The fields the dialog posts to ``/cropduster/upload/`` beside the file."""
    fields = {
        "md5": "",
        "sizes": dumps(config["sizes"]),
        "image_element_id": _text(config["elId"]),
        "upload_to": _text(config["uploadTo"]),
        "preview_width": _text(config["previewSize"]["w"]),
        "preview_height": _text(config["previewSize"]["h"]),
    }
    if config["standalone"]:
        fields["standalone"] = "on"
    return fields


def crop_fields(config, dumps):
    """The formset the dialog posts to ``/cropduster/crop/``."""
    image = config["image"] or {}
    thumbs = config["thumbs"]

    fields = {
        "crop-image_id": _text(image.get("id")),
        "crop-orig_image": _text(image.get("name")),
        "crop-orig_w": _text(image.get("width"), "0"),
        "crop-orig_h": _text(image.get("height"), "0"),
        "crop-sizes": dumps(config["sizes"]),
        "crop-thumbs": dumps(config["cropThumbs"]),
        "thumbs-TOTAL_FORMS": "%d" % len(thumbs),
        # Every crop the page opened with is an initial form;
        # ``apply_upload_reset`` zeroes the count after an upload because the
        # new image invalidates the existing crops.
        "thumbs-INITIAL_FORMS": "%d" % len(thumbs),
        "thumbs-MIN_NUM_FORMS": "0",
        "thumbs-MAX_NUM_FORMS": "1000",
    }
    if config["standalone"]:
        fields["crop-standalone"] = "on"

    for i, thumb in enumerate(thumbs):
        fields.update({
            "thumbs-%d-id" % i: _text(thumb["id"]),
            "thumbs-%d-name" % i: _text(thumb["name"]),
            "thumbs-%d-width" % i: _text(thumb["width"], "0"),
            "thumbs-%d-height" % i: _text(thumb["height"], "0"),
            "thumbs-%d-crop_x" % i: _text(thumb["crop_x"]),
            "thumbs-%d-crop_y" % i: _text(thumb["crop_y"]),
            "thumbs-%d-crop_w" % i: _text(thumb["crop_w"]),
            "thumbs-%d-crop_h" % i: _text(thumb["crop_h"]),
            "thumbs-%d-thumbs" % i: dumps(thumb["thumbs"]),
            "thumbs-%d-size" % i: dumps(thumb["size"]) if thumb["size"] else "",
        })
        # `changed` is a checkbox: unchecked means absent, not empty.
        if thumb["changed"]:
            fields["thumbs-%d-changed" % i] = "on"

    return fields


def apply_upload_reset(fields):
    """upload.js ``onSuccess(action == 'upload')``: blank the formset."""
    for name in list(fields):
        if not name.startswith("thumbs-"):
            continue
        if re.search(r"\d\-crop_", name) or re.search(r"-(width|height|thumbs)$", name):
            fields[name] = ""
        elif name == "thumbs-INITIAL_FORMS":
            fields[name] = "0"
    fields["crop-thumbs"] = ""


def apply_set_form_data(fields, data, dumps):
    """upload.js ``setFormData(data)``."""
    crop = data.get("crop")
    if isinstance(crop, dict):
        for name, value in crop.items():
            if isinstance(value, (dict, list)):
                if not value:
                    value = ""
                else:
                    value = dumps(value)
            if not value and re.search(r"(sizes|orig_w|orig_h)", name):
                continue
            fields["crop-%s" % name] = "" if value is None else str(value)

    thumbs = data.get("thumbs")
    if not isinstance(thumbs, list):
        return

    initial_form_count = 0
    for i, thumb in enumerate(thumbs):
        for name, value in thumb.items():
            if name == "id" and value:
                initial_form_count += 1
            if isinstance(value, (dict, list)):
                value = dumps(value)
            key = "thumbs-%d-%s" % (i, name)
            if name == "changed":
                # rendered as a checkbox
                if value and value not in ("off", "false", "0"):
                    fields[key] = "on"
                else:
                    fields.pop(key, None)
            else:
                fields[key] = "" if value is None else str(value)
    fields["thumbs-INITIAL_FORMS"] = str(initial_form_count)


def set_crop_box(fields, index, x, y, w, h):
    """upload.js ``cropBox.onChange``."""
    fields["thumbs-%d-crop_x" % index] = str(x)
    fields["thumbs-%d-crop_y" % index] = str(y)
    fields["thumbs-%d-crop_w" % index] = str(w)
    fields["thumbs-%d-crop_h" % index] = str(h)


# ---------------------------------------------------------------------------
# Recorder
# ---------------------------------------------------------------------------


class Recorder(object):

    def __init__(self, out_dir):
        self.out_dir = out_dir
        self.fixtures = {}
        self._media_root = None

    # -- environment ------------------------------------------------------

    def start_scenario(self):
        """Fresh MEDIA_ROOT + empty database + a fresh superuser and client."""
        from django.contrib.auth.models import User
        from django.core.management import call_command
        from django.test import Client, override_settings

        self.finish_scenario()

        self._media_root = tempfile.mkdtemp(prefix="legacy_wire_media_")
        self._override = override_settings(MEDIA_ROOT=self._media_root)
        self._override.enable()

        call_command("flush", interactive=False, verbosity=0,
                     allow_cascade=False, inhibit_post_migrate=False)

        user = User.objects.create_superuser("test", "test@test.com", "password")
        client = Client()
        client.force_login(user)
        return client

    def finish_scenario(self):
        if self._media_root is None:
            return
        self._override.disable()
        shutil.rmtree(self._media_root, ignore_errors=True)
        self._media_root = None

    # -- capture ----------------------------------------------------------

    def capture(self, name, description, response, method, path, post,
                files=None, setup=None):
        raw = response.content.decode("utf-8")
        normalized = normalize(raw)
        try:
            payload = stdlib_json.loads(normalized)
        except ValueError:
            raise AssertionError(
                "%s: response was not JSON (status %s):\n%s"
                % (name, response.status_code, raw[:2000]))

        meta = {
            "scenario": name,
            "description": description,
            "source": {
                "response": dict(RESPONSE_SOURCE),
                "request": REQUEST_SOURCE,
            },
            "request": {
                "method": method,
                "path": path,
                "post": normalize_obj(post),
                "files": files or {},
            },
            "response": {
                "status_code": response.status_code,
                "content_type": response.headers.get("Content-Type"),
            },
            "normalize": {
                "function": "tests.data.legacy_wire.record.normalize",
                "applies_to": "raw response body text, before json.loads",
                "rules": NORMALIZE_RULES,
                "not_normalized": [
                    "md5 digests (inputs are fixed files; digests are "
                    "reproducible)",
                    "database primary keys (each scenario runs against a "
                    "flushed database with reset sequences)",
                ],
            },
        }
        if setup:
            meta["setup"] = setup

        self.fixtures[name] = {"_meta": meta, "response": payload}
        # Later requests use values from this response, so return the original
        # paths rather than their normalized placeholders.
        return stdlib_json.loads(raw)

    def write(self):
        if not os.path.isdir(self.out_dir):
            os.makedirs(self.out_dir)
        for name, fixture in sorted(self.fixtures.items()):
            path = os.path.join(self.out_dir, "%s.json" % name)
            with io.open(path, "w", encoding="utf-8") as f:
                stdlib_json.dump(fixture, f, indent=2, sort_keys=True,
                                 ensure_ascii=False)
                f.write("\n")
        return sorted(self.fixtures)


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

INDEX_URL = "/cropduster/"
UPLOAD_URL = "/cropduster/upload/"
CROP_URL = "/cropduster/crop/"


def image_file(name):
    return io.open(os.path.join(TEST_IMG_DIR, name), "rb")


def open_dialog(client, sizes_json, upload_to, el_id, preview="800x500", **extra):
    """GET the dialog page so the recorded POSTs use the rendered form values."""
    params = {
        "sizes": sizes_json,
        "upload_to": upload_to,
        "el_id": el_id,
        "preview_size": preview,
    }
    params.update(extra)
    response = client.get(INDEX_URL, params)
    assert response.status_code == 200, response.status_code
    return response.content.decode("utf-8")


def record_upload_and_crop(rec):
    """(a) Author.headshot upload, (b) the follow-on crop POST."""
    from cropduster.utils import json as cjson
    from tests.models import Author

    sizes_json = cjson.dumps(Author.HEADSHOT_SIZES)
    upload_to = "author/headshots/%Y/%m"

    client = rec.start_scenario()
    config = dialog_config(open_dialog(client, sizes_json, upload_to, "id_headshot"))

    # (a) upload -------------------------------------------------------
    upload_post = upload_fields(config, cjson.dumps)
    with image_file("img.jpg") as f:
        response = client.post(UPLOAD_URL, dict(upload_post, image=f))
    upload_data = rec.capture(
        "upload_author_headshot",
        "Non-standalone upload of tests/data/img.jpg (674x800) for "
        "tests.models.Author.headshot (main 220x180 with an auto thumb "
        "110x90). This is the response upload.js feeds to setFormData().",
        response, "POST", UPLOAD_URL, upload_post,
        files={"image": "tests/data/img.jpg"})

    # (b) crop ---------------------------------------------------------
    crop_post = crop_fields(config, cjson.dumps)
    apply_upload_reset(crop_post)
    apply_set_form_data(crop_post, upload_data, cjson.dumps)
    # Jcrop's default centered box for a 220x180 (1.2222) size over 674x800
    set_crop_box(crop_post, 0, 0, 125, 674, 551)
    # The submit button's value, which jQuery Form serialized along with the
    # form. 4.x relabelled it in its response handler, for whichever index that
    # response left it on, and an upload goes through the same handler: on a
    # one-size field index 0 is also the last size, so the button reads
    # "Crop and Generate Thumbs" by the time this POST is built.
    crop_post["crop"] = "Crop and Generate Thumbs"

    response = client.post(CROP_URL, crop_post)
    rec.capture(
        "crop_author_headshot",
        "The crop POST upload.js sends after the upload above: crop-* fields "
        "from the upload response plus a one-form thumbs-* formset carrying "
        "the default centered crop (0, 125, 674, 551). The response carries "
        "the generated 'main' thumb and its auto child 'thumb'.",
        response, "POST", CROP_URL, crop_post,
        setup="Preceded by the upload_author_headshot request in the same "
              "session and MEDIA_ROOT.")

    rec.finish_scenario()


def record_second_size_suggest(rec):
    """(c1) Two-size formset, second size uncropped -> fit_to_crop suggestion."""
    from cropduster.utils import json as cjson
    from tests.models import Article

    sizes_json = cjson.dumps(Article.LEAD_IMAGE_SIZES)
    upload_to = "article/lead_image/%Y/%m"

    client = rec.start_scenario()
    config = dialog_config(open_dialog(client, sizes_json, upload_to, "id_lead_image"))

    upload_post = upload_fields(config, cjson.dumps)
    with image_file("img2.jpg") as f:
        response = client.post(UPLOAD_URL, dict(upload_post, image=f))
    upload_data = stdlib_json.loads(response.content.decode("utf-8"))

    crop_post = crop_fields(config, cjson.dumps)
    apply_upload_reset(crop_post)
    apply_set_form_data(crop_post, upload_data, cjson.dumps)
    # main is 600x480 (1.25); the centered box over 1300x1016 is 1270x1016
    set_crop_box(crop_post, 0, 15, 0, 1270, 1016)
    # thumbs-1 (no_height, w=600) is left uncropped: the user has not
    # navigated to it yet.
    crop_post["crop"] = "Crop and Continue"

    response = client.post(CROP_URL, crop_post)
    rec.capture(
        "crop_lead_image_suggest",
        "tests.models.Article.lead_image (main 600x480 + auto thumb, "
        "no_height w=600) cropped from tests/data/img2.jpg (1300x1016). "
        "Two-form formset: thumbs-0 (main) carries a crop, thumbs-1 "
        "(no_height) has no pk and no crop, so the view answers with a "
        "Size.fit_to_crop() suggestion for it (changed=true, id=null).",
        response, "POST", CROP_URL, crop_post,
        setup="Preceded by a standard non-standalone upload of "
              "tests/data/img2.jpg with the Article.lead_image sizes.")

    rec.finish_scenario()


def record_second_size_copy(rec):
    """(c2) Second size already saved and unchanged -> copy <name> to <name>_tmp."""
    from django.contrib.contenttypes.models import ContentType
    from django.core.files.storage import default_storage

    from cropduster.models import Image
    from cropduster.utils import json as cjson
    from tests.models import Article

    sizes_json = cjson.dumps(Article.LEAD_IMAGE_SIZES)
    upload_to = "article/lead_image/%Y/%m"

    client = rec.start_scenario()
    config = dialog_config(open_dialog(client, sizes_json, upload_to, "id_lead_image"))

    upload_post = upload_fields(config, cjson.dumps)
    with image_file("img2.jpg") as f:
        response = client.post(UPLOAD_URL, dict(upload_post, image=f))
    upload_data = stdlib_json.loads(response.content.decode("utf-8"))
    orig_image = upload_data["orig_image"]

    # Create the state of a saved Article: Thumb rows linked to an Image row
    # and a non-temporary file for every size.
    article = Article.objects.create(title="Legacy wire", lead_image=orig_image)
    article.lead_image.generate_thumbs()
    db_image = Image.objects.get(
        content_type=ContentType.objects.get_for_model(Article),
        object_id=article.pk, field_identifier="")
    thumb_ids = ",".join(str(pk) for pk in sorted(
        db_image.thumbs.values_list("pk", flat=True)))

    reopened = dialog_config(open_dialog(
        client, sizes_json, upload_to, "id_lead_image",
        id=db_image.pk, image=orig_image, thumbs=thumb_ids))

    crop_post = crop_fields(reopened, cjson.dumps)
    # The user re-crops main and submits a second time, so upload.js has
    # already checked both 'changed' checkboxes from the crop response that
    # preceded this one.
    set_crop_box(crop_post, 0, 0, 0, 1270, 1016)
    crop_post["thumbs-0-changed"] = "on"
    crop_post["thumbs-1-changed"] = "on"
    crop_post["crop"] = "Crop and Continue"

    response = client.post(CROP_URL, crop_post)

    tmp_path = db_image.get_image_path("no_height", tmp=True)
    assert default_storage.exists(tmp_path), (
        "crop_lead_image_copy did not reach the copy branch: %s was "
        "not written" % tmp_path)

    rec.capture(
        "crop_lead_image_copy",
        "Second-size navigation against an Article that already has saved "
        "thumbs. thumbs-0 (main) has changed crop coordinates; thumbs-1 "
        "(no_height) keeps its stored crop and only its 'changed' checkbox "
        "differs, so the view takes the elif branch and copies no_height.jpg "
        "to no_height_tmp.jpg instead of regenerating it.",
        response, "POST", CROP_URL, crop_post,
        setup=(
            "Upload tests/data/img2.jpg for Article.lead_image, then create "
            "an Article with lead_image set to the uploaded original and call "
            "CropDusterImageFieldFile.generate_thumbs() so that 'main', its "
            "auto child 'thumb' and 'no_height' all exist in the database "
            "with files on disk. The dialog is then re-opened with "
            "?id=<image pk>&image=<orig>&thumbs=<all thumb pks>."))

    rec.finish_scenario()


# The exact size object a standalone rich-text-editor client builds by hand
# for its crop POST; key order matches JSON.stringify of the object literal.
STANDALONE_SIZE = {
    "name": "crop",
    "w": None,
    "h": None,
    "min_w": 1,
    "min_h": 1,
    "max_w": None,
    "max_h": None,
    "retina": 0,
    "label": "Crop",
    "required": True,
    "__type__": "Size",
}


def js_stringify(obj):
    """json.dumps with JSON.stringify's separators."""
    return stdlib_json.dumps(obj, separators=(",", ":"))


def record_standalone(rec):
    """(d) Replay a standalone client's upload and crop POSTs verbatim."""
    client = rec.start_scenario()

    # The upload POST: three fields, nothing else.
    upload_post = {
        "standalone": "1",
        "upload_to": "img/posts/%Y/%m",
    }
    with image_file("img.jpg") as f:
        response = client.post(UPLOAD_URL, dict(upload_post, image=f))
    upload_data = rec.capture(
        "standalone_upload",
        "A standalone client's upload: POST /cropduster/upload/ with only "
        "image, standalone=1 and upload_to. Requires cropduster.standalone "
        "(python-xmp-toolkit + exempi). The response contains crop.image_id, "
        "crop.sizes and a one-element thumbs list whose name is the md5 "
        "prefix of the generated crop.",
        response, "POST", UPLOAD_URL, upload_post,
        files={"image": "tests/data/img.jpg"},
        setup="Field-for-field replay of a downstream rich-text editor's "
              "standalone upload POST.")

    # The crop POST: a hand-built formset, not the dialog's.
    crop = {"x": 0, "y": 0, "width": upload_data["width"],
            "height": upload_data["height"], "unit": "px"}
    x1, y1 = crop["x"], crop["y"]
    x2, y2 = crop["x"] + crop["width"], crop["y"] + crop["height"]

    crop_post = {
        "crop-image_id": "%s" % upload_data["crop"]["image_id"],
        "crop-orig_image": upload_data["orig_image"],
        "crop-orig_w": "%s" % upload_data["orig_w"],
        "crop-orig_h": "%s" % upload_data["orig_h"],
        "crop-standalone": "on",
        "crop-sizes": js_stringify([STANDALONE_SIZE]),
        "thumbs-TOTAL_FORMS": "1",
        "thumbs-INITIAL_FORMS": "1",
        "thumbs-MIN_NUM_FORMS": "0",
        "thumbs-MAX_NUM_FORMS": "1000",
        "thumbs-0-name": "crop",
        "thumbs-0-crop_x": "%s" % x1,
        "thumbs-0-crop_y": "%s" % y1,
        "thumbs-0-crop_w": "%s" % (x2 - x1),
        "thumbs-0-crop_h": "%s" % (y2 - y1),
        "thumbs-0-size": js_stringify(STANDALONE_SIZE),
    }

    response = client.post(CROP_URL, crop_post)
    rec.capture(
        "standalone_crop",
        "A standalone client's crop: a hand-built crop POST that never went "
        "through the dialog. No thumbs-0-id is sent even though "
        "INITIAL_FORMS=1, so ThumbFormSet._construct_form rewrites the pk to "
        "None and the view's 'standalone and not cropped_thumbs' fallback "
        "re-saves the initial form. Downstream clients read "
        "data.thumbs[0].id from this response.",
        response, "POST", CROP_URL, crop_post,
        setup="Field-for-field replay of a downstream rich-text editor's "
              "standalone crop POST, preceded by standalone_upload.")

    rec.finish_scenario()


def record_errors(rec):
    """(e) The HTTP-200 {"error": html} envelopes."""
    from cropduster.utils import json as cjson
    from tests.models import Author

    sizes_json = cjson.dumps(Author.HEADSHOT_SIZES)
    upload_to = "author/headshots/%Y/%m"

    client = rec.start_scenario()
    config = dialog_config(open_dialog(client, sizes_json, upload_to, "id_headshot"))

    upload_post = upload_fields(config, cjson.dumps)
    with image_file("transparent.png") as f:
        response = client.post(UPLOAD_URL, dict(upload_post, image=f))
    rec.capture(
        "error_upload_min_size",
        "Upload rejected by clean_upload_data()'s min-size check: "
        "tests/data/transparent.png is 255x80 but Author.headshot requires "
        "at least 220x180. HTTP 200 with an {'error': html} body.",
        response, "POST", UPLOAD_URL, upload_post,
        files={"image": "tests/data/transparent.png"})

    # CropForm.sizes is the only required field; without it the form is
    # invalid before the formset is even constructed.
    crop_post = {
        "crop-image_id": "",
        "crop-orig_image": "author/headshots/2026/01/img/original.jpg",
        "crop-orig_w": "674",
        "crop-orig_h": "800",
        "crop-thumbs": "",
        "thumbs-TOTAL_FORMS": "1",
        "thumbs-INITIAL_FORMS": "0",
        "thumbs-MIN_NUM_FORMS": "0",
        "thumbs-MAX_NUM_FORMS": "1000",
        "thumbs-0-id": "",
        "thumbs-0-name": "main",
        "thumbs-0-width": "",
        "thumbs-0-height": "",
        "thumbs-0-crop_x": "0",
        "thumbs-0-crop_y": "125",
        "thumbs-0-crop_w": "674",
        "thumbs-0-crop_h": "551",
        "thumbs-0-thumbs": "",
        "thumbs-0-size": "",
        "crop": "Crop and Continue",
    }
    response = client.post(CROP_URL, crop_post)
    rec.capture(
        "error_crop_invalid_form",
        "Crop POST with crop-sizes missing, so CropForm is invalid and the "
        "view returns json_error(forms=[crop_form], log=True). HTTP 200 with "
        "an {'error': html} body whose field names are wrapped in "
        "<span class=\"error-field error-<name>\">.",
        response, "POST", CROP_URL, crop_post)

    rec.finish_scenario()


SCENARIO_GROUPS = [
    record_upload_and_crop,
    record_second_size_suggest,
    record_second_size_copy,
    record_standalone,
    record_errors,
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=DATA_DIR,
                        help="directory to write the fixtures into")
    parser.add_argument(
        "--force", action="store_true",
        help="overwrite fixtures that are already there, replacing 4.15.0's "
             "recorded responses with this tree's")
    args = parser.parse_args()

    out_dir = os.path.abspath(args.out)
    existing = sorted(
        name for name in os.listdir(out_dir) if name.endswith(".json")
    ) if os.path.isdir(out_dir) else []
    if existing and not args.force:
        parser.error(
            "%s already contains %d fixtures whose responses were recorded "
            "from 4.15.0 and cannot be reproduced from this tree. Write "
            "somewhere else with --out, or pass --force to discard them." % (
                out_dir, len(existing)))

    bootstrap_django()

    rec = Recorder(out_dir)
    for group in SCENARIO_GROUPS:
        group(rec)
    written = rec.write()

    sys.stderr.write("wrote %d fixtures to %s:\n" % (len(written), rec.out_dir))
    for name in written:
        sys.stderr.write("  %s.json\n" % name)


if __name__ == "__main__":
    main()
