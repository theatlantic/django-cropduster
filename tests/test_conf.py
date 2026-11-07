import math

from django import test
from django.core.exceptions import ImproperlyConfigured

from cropduster import conf as cropduster_conf
from cropduster import settings as cropduster_settings_module
from cropduster.conf import get_jpeg_quality, settings as cropduster_settings


class TestLiveSettings(test.SimpleTestCase):

    def test_defaults(self):
        self.assertEqual(cropduster_settings.CROPDUSTER_PREVIEW_WIDTH, 800)
        self.assertEqual(cropduster_settings.CROPDUSTER_PREVIEW_HEIGHT, 500)
        self.assertIs(cropduster_settings.CROPDUSTER_RETAIN_METADATA, False)
        self.assertIs(cropduster_settings.JPEG_SAVE_ICC_SUPPORTED, True)

    def test_override_settings_is_seen_without_reload(self):
        with test.override_settings(CROPDUSTER_PREVIEW_WIDTH=123):
            self.assertEqual(cropduster_settings.CROPDUSTER_PREVIEW_WIDTH, 123)
        self.assertEqual(cropduster_settings.CROPDUSTER_PREVIEW_WIDTH, 800)

    def test_module_attribute_access_is_live(self):
        with test.override_settings(CROPDUSTER_CREATE_THUMBS=False):
            self.assertIs(
                cropduster_settings_module.CROPDUSTER_CREATE_THUMBS, False)
        self.assertIs(cropduster_settings_module.CROPDUSTER_CREATE_THUMBS, True)

    def test_module_raises_attribute_error_for_unknown_setting(self):
        with self.assertRaises(AttributeError):
            cropduster_settings_module.CROPDUSTER_NOT_A_SETTING

    def test_media_root_defaults_to_django_media_root(self):
        with test.override_settings(MEDIA_ROOT='/tmp/somewhere'):
            self.assertEqual(
                cropduster_settings.CROPDUSTER_MEDIA_ROOT, '/tmp/somewhere')
        with test.override_settings(CROPDUSTER_MEDIA_ROOT='/tmp/elsewhere'):
            self.assertEqual(
                cropduster_settings.CROPDUSTER_MEDIA_ROOT, '/tmp/elsewhere')


class TestModuleIntrospection(test.SimpleTestCase):

    def test_star_import_covers_the_live_settings(self):
        namespace = {}
        exec('from cropduster.settings import *', namespace)

        self.assertEqual(namespace['CROPDUSTER_PREVIEW_WIDTH'], 800)
        self.assertEqual(namespace['CROPDUSTER_APP_LABEL'], 'cropduster')
        self.assertIs(namespace['get_jpeg_quality'], get_jpeg_quality)

    def test_dir_lists_the_live_settings(self):
        for module in (cropduster_settings_module, cropduster_conf):
            self.assertIn('CROPDUSTER_CREATE_THUMBS', dir(module))
            self.assertIn('CROPDUSTER_DB_PREFIX', dir(module))


class TestAppLabelConstants(test.SimpleTestCase):

    def test_defaults(self):
        self.assertEqual(
            cropduster_settings_module.CROPDUSTER_APP_LABEL, 'cropduster')
        self.assertEqual(
            cropduster_settings_module.CROPDUSTER_DB_PREFIX, 'cropduster4')

    def test_v4_aliases_agree(self):
        self.assertEqual(
            cropduster_settings_module.CROPDUSTER_V4_APP_LABEL,
            cropduster_settings_module.CROPDUSTER_APP_LABEL)
        self.assertEqual(
            cropduster_settings_module.CROPDUSTER_V4_DB_PREFIX,
            cropduster_settings_module.CROPDUSTER_DB_PREFIX)

    def test_not_affected_by_override_settings(self):
        with test.override_settings(CROPDUSTER_APP_LABEL='somethingelse'):
            self.assertEqual(
                cropduster_settings.CROPDUSTER_APP_LABEL, 'cropduster')

    def test_models_use_them(self):
        from cropduster.models import Image, Thumb

        self.assertEqual(Image._meta.app_label, 'cropduster')
        self.assertEqual(Thumb._meta.db_table, 'cropduster4_thumb')


class TestJpegQuality(test.SimpleTestCase):

    def test_default_scales_with_pixel_count(self):
        get_quality = cropduster_settings.get_jpeg_quality
        self.assertEqual(get_quality(2000, 2000), 80)
        self.assertEqual(get_quality(1200, 1200), 85)
        self.assertEqual(get_quality(100, 100), 90)

    def test_numeric_setting(self):
        with test.override_settings(CROPDUSTER_JPEG_QUALITY=42):
            self.assertEqual(
                cropduster_settings.get_jpeg_quality(100, 100), 42)

    def test_callable_setting(self):
        quality = lambda width, height: int(math.sqrt(width * height))
        with test.override_settings(CROPDUSTER_JPEG_QUALITY=quality):
            self.assertEqual(cropduster_settings.get_jpeg_quality(4, 9), 6)

    def test_invalid_setting(self):
        with test.override_settings(CROPDUSTER_JPEG_QUALITY='high'):
            with self.assertRaises(ImproperlyConfigured):
                cropduster_settings.get_jpeg_quality(100, 100)


class TestGifsiclePathCache(test.SimpleTestCase):

    def test_explicit_setting_wins(self):
        with test.override_settings(
                CROPDUSTER_GIFSICLE_PATH='/nowhere/gifsicle'):
            self.assertEqual(
                cropduster_settings.CROPDUSTER_GIFSICLE_PATH,
                '/nowhere/gifsicle')

    def test_discovered_path_is_cached_and_reset_on_setting_changed(self):
        discovered = cropduster_settings.CROPDUSTER_GIFSICLE_PATH
        cropduster_settings._gifsicle_path = '/cached/gifsicle'
        self.assertEqual(
            cropduster_settings.CROPDUSTER_GIFSICLE_PATH, '/cached/gifsicle')

        with test.override_settings(CROPDUSTER_PREVIEW_WIDTH=1):
            pass

        self.assertEqual(
            cropduster_settings.CROPDUSTER_GIFSICLE_PATH, discovered)
