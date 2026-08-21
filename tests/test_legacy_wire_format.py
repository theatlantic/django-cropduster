"""Replay the recorded Cropduster 4.15 requests against the current views.

The scenario functions in ``record.py`` construct the requests used for the
recordings. Normalized responses must match except for the documented
``crop.sizes`` correction.
"""

import json as stdlib_json
import os
import re
import shutil
import tempfile

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import Client, TransactionTestCase, override_settings

from tests.data.legacy_wire import record

from .helpers import FILESYSTEM_STORAGES


FIXTURE_DIR = os.path.dirname(os.path.abspath(record.__file__))

#: Every scenario the recorder writes, by the group that produces it.
SCENARIOS = {
    record.record_upload_and_crop: ['upload_author_headshot', 'crop_author_headshot'],
    record.record_second_size_suggest: ['crop_lead_image_suggest'],
    record.record_second_size_copy: ['crop_lead_image_copy'],
    record.record_standalone: ['standalone_upload', 'standalone_crop'],
    record.record_errors: ['error_upload_min_size', 'error_crop_invalid_form'],
}

SANCTIONED_DELTA = """
The crop response's ``crop.sizes`` was recorded as null because 4.15.0's
``CropForm.clean_sizes()`` parsed the submitted sizes and then returned None
instead of them. Returning them is the one sanctioned behavior change of the
5.0 backend cleanup, so the recorded null is compared against the sizes that
were posted rather than against the current response.
"""


def load_fixture(name):
    with open(os.path.join(FIXTURE_DIR, '%s.json' % name)) as f:
        return stdlib_json.load(f)


def normalize(text, rules):
    """Apply a fixture's own recorded normalization rules to a response body."""
    for rule in rules:
        text = re.sub(rule['pattern'], rule['replacement'], text)
    return text


@override_settings(STORAGES=FILESYSTEM_STORAGES)
class LegacyWireFormatTest(TransactionTestCase):
    """
    Compare responses through the same interface used by ``record.Recorder``.

    Each scenario starts with an empty database because the fixtures contain
    primary keys.
    """

    _media_root = None

    def tearDown(self):
        self.finish_scenario()

    # -- the recorder interface -------------------------------------------

    def start_scenario(self):
        """Fresh MEDIA_ROOT + empty database + a fresh superuser and client."""
        self.finish_scenario()

        self._media_root = tempfile.mkdtemp(prefix='legacy_wire_media_')
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

    def capture(self, name, description, response, method, path, post,
                files=None, setup=None):
        fixture = load_fixture(name)
        meta = fixture['_meta']

        # Compare the request as well as the response so client-side form
        # serialization remains compatible with the recording.
        self.assertEqual(record.normalize_obj(post), meta['request']['post'], name)
        self.assertEqual(files or {}, meta['request']['files'], name)

        self.assertEqual(response.status_code, meta['response']['status_code'], name)
        self.assertEqual(
            response.headers.get('Content-Type'), meta['response']['content_type'], name)

        raw = response.content.decode('utf-8')
        actual = stdlib_json.loads(normalize(raw, meta['normalize']['rules']))
        expected = fixture['response']

        if path == record.CROP_URL and 'crop' in expected:
            self.assert_sizes_delta(name, post, actual, expected)

        self.assertEqual(actual, expected, name)

        # Scenarios chain: return the real paths, not the placeholders.
        return stdlib_json.loads(raw)

    # -- the one documented difference ------------------------------------

    def assert_sizes_delta(self, name, post, actual, expected):
        """Compare ``crop.sizes`` against the request, and drop it from both."""
        self.assertIsNone(
            expected['crop']['sizes'],
            "%s: the fixture should contain 4.15.0's null sizes. %s"
            % (name, SANCTIONED_DELTA))
        self.assertEqual(
            actual['crop'].pop('sizes'), stdlib_json.loads(post['crop-sizes']),
            "%s: crop.sizes must echo the sizes that were posted. %s"
            % (name, SANCTIONED_DELTA))
        expected['crop'] = {
            key: value for key, value in expected['crop'].items() if key != 'sizes'}

    # -- the scenarios ----------------------------------------------------

    def test_upload_and_crop(self):
        record.record_upload_and_crop(self)

    def test_second_size_suggest(self):
        record.record_second_size_suggest(self)

    def test_second_size_copy(self):
        record.record_second_size_copy(self)

    def test_standalone(self):
        record.record_standalone(self)

    def test_errors(self):
        record.record_errors(self)

    def test_every_fixture_is_replayed(self):
        replayed = {name for names in SCENARIOS.values() for name in names}
        recorded = {
            os.path.splitext(entry)[0] for entry in os.listdir(FIXTURE_DIR)
            if entry.endswith('.json')}
        self.assertEqual(recorded, replayed)
