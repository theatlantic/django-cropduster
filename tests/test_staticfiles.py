"""
Verify Cropduster's assets under ``ManifestStaticFilesStorage``.

The 5.0 JavaScript bundle contains a ``sourceMappingURL`` reference.
``collectstatic`` fails if that file is not collected and rewritten, so these
tests run the same post-processing used by a deployment.

Only Cropduster's static directories are included. Assets from unrelated
applications should not affect these checks.
"""

import json
import os
import re
import tempfile

from django.contrib.staticfiles.storage import (
    ManifestStaticFilesStorage, staticfiles_storage)
from django.core.management import call_command
from django.templatetags.static import static
from django.test import SimpleTestCase, override_settings


CROPDUSTER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATICFILES_DIRS = [
    os.path.join(CROPDUSTER_DIR, 'cropduster', 'static'),
    os.path.join(CROPDUSTER_DIR, 'cropduster', 'standalone', 'static'),
]

BUNDLE = 'cropduster/dist/cropduster.js'
STYLESHEET = 'cropduster/dist/cropduster.css'
SOURCE_MAP = 'cropduster/dist/cropduster.js.map'

HASHED = re.compile(r'^cropduster/dist/cropduster\.[0-9a-f]{12}\.(js|css)$')


class ManifestStaticFilesTest(SimpleTestCase):
    """Each test collects into its own STATIC_ROOT, since collection writes."""

    def setUp(self):
        self.static_root = tempfile.TemporaryDirectory()
        self.addCleanup(self.static_root.cleanup)
        overrides = override_settings(
            STATIC_ROOT=self.static_root.name,
            STATIC_URL='/static/',
            STATICFILES_DIRS=STATICFILES_DIRS,
            STATICFILES_FINDERS=[
                'django.contrib.staticfiles.finders.FileSystemFinder',
            ],
            STORAGES={
                'default': {
                    'BACKEND': 'django.core.files.storage.FileSystemStorage',
                },
                'staticfiles': {
                    'BACKEND': 'django.contrib.staticfiles.storage.'
                               'ManifestStaticFilesStorage',
                },
            },
        )
        overrides.enable()
        self.addCleanup(overrides.disable)
        call_command('collectstatic', interactive=False, verbosity=0)

    def manifest(self):
        path = os.path.join(self.static_root.name, 'staticfiles.json')
        with open(path) as f:
            return json.load(f)['paths']

    def collected(self, name):
        """The hashed file one logical path was collected as."""
        hashed = self.manifest()[name]
        path = os.path.join(self.static_root.name, hashed)
        self.assertTrue(os.path.exists(path), "%s was not written" % hashed)
        return hashed, path

    def test_the_bundle_and_its_stylesheet_are_hashed(self):
        """
        Hash both files named by ``CropDusterWidget.media``.

        Vite emits fixed source names; manifest storage adds hashes during
        collection. The bundle therefore uses no hashed chunks of its own.
        """
        for name in (BUNDLE, STYLESHEET):
            hashed, _ = self.collected(name)
            self.assertRegex(hashed, HASHED)

    def test_static_resolves_to_the_hashed_bundle(self):
        """Return the hashed URL used by the widget's production script."""
        self.assertEqual(
            static(BUNDLE),
            '/static/%s' % self.manifest()[BUNDLE])

    def test_the_source_map_comment_is_rewritten(self):
        """
        Manifest storage rewrites ``//# sourceMappingURL=`` like any other
        reference, so the map has to be collected too or post-processing fails.
        """
        hashed_map = self.manifest()[SOURCE_MAP]
        _, path = self.collected(BUNDLE)
        with open(path) as f:
            comment = f.read().rsplit('sourceMappingURL=', 1)[1].strip()

        self.assertEqual(comment, os.path.basename(hashed_map))

    def test_the_dialog_and_widget_assets_survive(self):
        """
        Collect the other runtime assets used by the widget and dialog.

        These include the CKEditor plugin, the upload view's placeholder GIF,
        and the two compatibility shims for 4.x asset bundles.
        """
        for name in ('ckeditor/ckeditor/plugins/cropduster/plugin.js',
                     'ckeditor/ckeditor/plugins/cropduster/dialogs/cropduster.js',
                     'cropduster/img/blank.gif',
                     'cropduster/js/cropduster.js',
                     'cropduster/js/jsrender.js'):
            self.collected(name)

    def test_the_storage_the_admin_uses_is_the_manifest_one(self):
        """Confirm that the test uses ``ManifestStaticFilesStorage``."""
        self.assertIsInstance(staticfiles_storage, ManifestStaticFilesStorage)
