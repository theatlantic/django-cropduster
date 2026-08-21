"""Check Cropduster without the ``standalone`` extra.

The ``py312-dj52-noxmp`` tox env runs this module against
``tests.settings_noxmp`` without python-xmp-toolkit installed. The normal test
suite also runs it, but the ``without_libxmp`` fixture blocks the import there.
This checks the missing-dependency behavior in every test environment.
"""

import importlib
import os
import sys

from django import test
from django.apps import apps
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.contrib.auth.models import User
from django.urls import clear_url_caches, resolve, reverse

import PIL.Image
import pytest

import cropduster.urls
from cropduster.exceptions import CropDusterConfigurationError
from cropduster.models import Image, Size, StandaloneImage
from cropduster.standalone import NOT_INSTALLED_MESSAGE, standalone_available
from cropduster.utils import json
from cropduster import views

from .helpers import CropdusterTestCaseMediaMixin


#: Modules that import libxmp directly or through ``metadata.py``.
XMP_DEPENDENT_MODULES = (
    'cropduster.standalone.views',
    'cropduster.standalone.metadata',
)


class LibxmpBlocker:
    """A meta path finder that makes ``import libxmp`` fail."""

    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'libxmp' or fullname.startswith('libxmp.'):
            raise ImportError("libxmp is blocked by %s" % type(self).__name__)
        return None


def reload_urlconf():
    """Reload the URLconf after changing standalone availability.

    Reloading ``cropduster.urls`` is not sufficient because the
    ``URLResolver`` created by ``include()`` caches its ``url_patterns``.
    Clearing the URL caches does not reset that property, so the root URLconf
    must also be reloaded.
    """
    importlib.reload(cropduster.urls)
    importlib.reload(importlib.import_module(settings.ROOT_URLCONF))
    clear_url_caches()


@pytest.fixture(autouse=True)
def without_libxmp():
    """Make libxmp unavailable for one test.

    A test running with the extra installed cannot uninstall it, so the fixture
    blocks the import instead. ``cropduster.urls`` selects its standalone view
    while being imported, which requires reloading the URLconf before and after
    the test.
    """
    blocker = LibxmpBlocker()
    sys.meta_path.insert(0, blocker)
    evicted = {
        name: sys.modules.pop(name)
        for name in list(sys.modules)
        if name == 'libxmp' or name.startswith('libxmp.') or name in XMP_DEPENDENT_MODULES}
    reload_urlconf()
    try:
        yield
    finally:
        sys.meta_path.remove(blocker)
        sys.modules.update(evicted)
        reload_urlconf()


class TestImportsWithoutTheExtra(test.SimpleTestCase):

    def test_metadata_reports_the_missing_library(self):
        with self.assertRaises(ImproperlyConfigured):
            importlib.import_module('cropduster.standalone.metadata')

    def test_standalone_is_reported_unavailable(self):
        self.assertFalse(standalone_available())

    def test_the_standalone_model_is_still_registered(self):
        self.assertIs(apps.get_model('cropduster', 'StandaloneImage'), StandaloneImage)

    def test_the_core_modules_are_usable(self):
        for name in ('cropduster.models', 'cropduster.fields', 'cropduster.views'):
            self.assertIn(name, sys.modules)
        self.assertTrue(Image._meta.get_field('image'))


class TestStandaloneUrl(test.SimpleTestCase):

    def test_the_route_still_reverses(self):
        self.assertTrue(reverse('cropduster-standalone'))

    def test_the_view_names_the_missing_extra(self):
        url = reverse('cropduster-standalone')
        request = test.RequestFactory().get(url)

        with self.assertRaises(CropDusterConfigurationError) as caught:
            resolve(url).func(request)

        self.assertEqual(str(caught.exception), NOT_INSTALLED_MESSAGE)


class TestStandaloneEntryPoints(CropdusterTestCaseMediaMixin, test.TestCase):

    def setUp(self):
        super(TestStandaloneEntryPoints, self).setUp()
        self.factory = test.RequestFactory()
        self.user = User.objects.create_superuser('test', 'test@test.com', 'password')

    def test_save_size_refuses_standalone(self):
        db_image = Image(image=self.create_unique_image('img.jpg'))

        with self.assertRaises(CropDusterConfigurationError) as caught:
            db_image.save_size(Size('crop'), image=PIL.Image.new('RGB', (100, 100)),
                               standalone=True)

        self.assertEqual(str(caught.exception), NOT_INSTALLED_MESSAGE)

    def test_upload_returns_the_error_in_the_legacy_json_shape(self):
        with open(os.path.join(self.TEST_IMG_DIR, 'img.jpg'), 'rb') as img_file:
            request = self.factory.post(reverse('cropduster-upload'), {
                'image': img_file,
                'upload_to': 'test',
                'standalone': 'on',
                'md5': '',
            })
        request.user = self.user

        response = views.upload(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        data = json.loads(response.content)
        self.assertIn(NOT_INSTALLED_MESSAGE, data['error'])
        self.assertEqual(StandaloneImage.objects.count(), 0)

    def test_crop_returns_the_error_in_the_legacy_json_shape(self):
        request = self.factory.post(reverse('cropduster-crop'), {
            'crop-image_id': '',
            'crop-orig_image': '',
            'crop-sizes': '[]',
            'crop-thumbs': '{}',
            'crop-standalone': 'on',
        })
        request.user = self.user

        response = views.crop(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        data = json.loads(response.content)
        self.assertIn(NOT_INSTALLED_MESSAGE, data['error'])
