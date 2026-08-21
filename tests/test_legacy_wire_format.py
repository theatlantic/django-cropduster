"""Check the recorded Cropduster 4.15 request and response fixtures.

These tests read the fixture files rather than replaying the recorded
requests, so they do not depend on the upload and crop implementation.
"""

import json
import os

from django import test

from tests.data.legacy_wire import record


FIXTURE_DIR = os.path.dirname(os.path.abspath(record.__file__))
FIXTURES = {
    "crop_author_headshot",
    "crop_lead_image_copy",
    "crop_lead_image_suggest",
    "error_crop_invalid_form",
    "error_upload_min_size",
    "standalone_crop",
    "standalone_upload",
    "upload_author_headshot",
}


def load_fixture(name):
    with open(os.path.join(FIXTURE_DIR, "%s.json" % name)) as fixture_file:
        return json.load(fixture_file)


class LegacyWireFixtureTest(test.SimpleTestCase):

    def test_fixture_inventory_is_explicit(self):
        recorded = {
            os.path.splitext(name)[0]
            for name in os.listdir(FIXTURE_DIR)
            if name.endswith(".json")
        }
        self.assertEqual(recorded, FIXTURES)

    def test_every_response_names_its_4_15_source(self):
        for name in sorted(FIXTURES):
            with self.subTest(name=name):
                fixture = load_fixture(name)
                meta = fixture["_meta"]
                self.assertEqual(meta["scenario"], name)
                self.assertEqual(
                    meta["source"]["response"], record.RESPONSE_SOURCE
                )
                self.assertEqual(meta["source"]["request"], record.REQUEST_SOURCE)
                self.assertEqual(meta["normalize"]["rules"], record.NORMALIZE_RULES)

    def test_every_response_keeps_the_legacy_http_contract(self):
        for name in sorted(FIXTURES):
            with self.subTest(name=name):
                fixture = load_fixture(name)
                response = fixture["_meta"]["response"]
                request = fixture["_meta"]["request"]
                self.assertEqual(request["method"], "POST")
                self.assertIn(
                    request["path"],
                    (record.UPLOAD_URL, record.CROP_URL),
                )
                self.assertEqual(response["status_code"], 200)
                self.assertEqual(response["content_type"], "application/json")
                self.assertIsInstance(fixture["response"], dict)
