import contextlib
import sys
from unittest import mock

from django import test
from django.apps import apps
from django.contrib import admin
from django.core import checks
from django.contrib.contenttypes.admin import GenericInlineModelAdminChecks

from cropduster.checks import (
    check_api_permission, check_app_config, check_dialog_mode,
    check_metadata_only_renderer, check_thumbor_media_url, check_url_renderer)

from .models import Article
from .test_renderers import requires_libthumbor


class LibthumborBlocker:

    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'libthumbor' or fullname.startswith('libthumbor.'):
            raise ImportError('libthumbor is blocked for this test')
        return None


@contextlib.contextmanager
def without_libthumbor():
    blocker = LibthumborBlocker()
    sys.meta_path.insert(0, blocker)
    evicted = {
        name: sys.modules.pop(name)
        for name in list(sys.modules)
        if name == 'libthumbor' or name.startswith('libthumbor.')
    }
    try:
        yield
    finally:
        sys.meta_path.remove(blocker)
        sys.modules.update(evicted)


class TestAppConfigCheck(test.SimpleTestCase):

    def test_passes_for_the_frozen_label(self):
        self.assertEqual(check_app_config(), [])

    def test_e010_for_an_overridden_label(self):
        with mock.patch(
                'cropduster.checks.CROPDUSTER_APP_LABEL', 'cropduster_v4'):
            errors = check_app_config()

        self.assertEqual([error.id for error in errors], ['cropduster.E010'])
        self.assertIn('cropduster_v4', errors[0].msg)
        self.assertIn('CROPDUSTER_DB_PREFIX', errors[0].hint)


class TestAppConfig(test.SimpleTestCase):

    def test_label_matches_the_models(self):
        from cropduster.models import Image

        app_config = apps.get_app_config(Image._meta.app_label)
        self.assertEqual(app_config.name, 'cropduster')

    def test_standalone_has_no_config_of_its_own(self):
        standalone_config = apps.get_app_config('standalone')
        self.assertEqual(
            standalone_config.name, 'cropduster.standalone')
        self.assertNotEqual(standalone_config.label, 'cropduster')
        self.assertEqual(list(standalone_config.get_models()), [])


class TestInlineAdminChecks(test.SimpleTestCase):

    inline_cls = Article._meta.get_field(
        'lead_image').get_inline_admin_formset()

    def test_generated_inline_passes_checks(self):
        self.assertEqual(self.inline_cls(Article, admin.site).check(), [])

    def test_thumbs_is_what_the_filter_is_for(self):
        fieldset_fields = self.inline_cls.fieldsets[0][1]['fields']
        self.assertIn('thumbs', fieldset_fields)

    def test_stock_checks_class_rejects_the_inline(self):
        unfiltered_cls = type('UnfilteredInline', (self.inline_cls,), {
            'checks_class': GenericInlineModelAdminChecks,
        })

        errors = unfiltered_cls(Article, admin.site).check()
        self.assertEqual([error.id for error in errors], ['admin.E013'])


class TestUrlRendererCheck(test.SimpleTestCase):

    def test_default_renderer_passes(self):
        self.assertEqual(check_url_renderer(), [])

    def test_unimportable_backend_is_e001(self):
        with test.override_settings(CROPDUSTER_URL_RENDERER='nope.Renderer'):
            errors = check_url_renderer()
        self.assertEqual([error.id for error in errors], ['cropduster.E001'])

    def test_invalid_file_renderer_options_are_e001(self):
        spec = {
            'BACKEND': 'cropduster.renderers.FileRenderer',
            'OPTIONS': {'nope': True},
        }
        with test.override_settings(CROPDUSTER_URL_RENDERER=spec):
            errors = check_url_renderer()
        self.assertEqual([error.id for error in errors], ['cropduster.E001'])

    @requires_libthumbor
    def test_non_text_security_key_is_e001(self):
        with test.override_settings(
                CROPDUSTER_URL_RENDERER='cropduster.renderers.ThumborRenderer',
                CROPDUSTER_THUMBOR={
                    'SERVER': 'https://thumb.example.com/',
                    'SECURITY_KEY': 5,
                }):
            errors = check_url_renderer()
        self.assertEqual([error.id for error in errors], ['cropduster.E001'])

    @requires_libthumbor
    def test_missing_thumbor_server_is_e001(self):
        with test.override_settings(
                CROPDUSTER_URL_RENDERER='cropduster.renderers.ThumborRenderer',
                CROPDUSTER_THUMBOR={}):
            errors = check_url_renderer()
        self.assertEqual([error.id for error in errors], ['cropduster.E001'])
        self.assertIn("CROPDUSTER_THUMBOR['SERVER']", errors[0].msg)

    def test_missing_thumbor_extra_is_e001(self):
        with without_libthumbor():
            with test.override_settings(
                    CROPDUSTER_URL_RENDERER=(
                        'cropduster.renderers.ThumborRenderer')):
                errors = check_url_renderer()
        self.assertEqual([error.id for error in errors], ['cropduster.E001'])
        self.assertIn('django-cropduster[thumbor]', errors[0].msg)


class TestMetadataOnlyCheck(test.SimpleTestCase):

    def test_writing_thumbs_passes(self):
        self.assertEqual(check_metadata_only_renderer(), [])

    def test_file_renderer_is_w002_without_derivative_files(self):
        with test.override_settings(CROPDUSTER_CREATE_THUMBS=False):
            errors = check_metadata_only_renderer()
        self.assertEqual([error.id for error in errors], ['cropduster.W002'])

    @requires_libthumbor
    def test_thumbor_can_render_without_derivative_files(self):
        with test.override_settings(
                CROPDUSTER_CREATE_THUMBS=False,
                CROPDUSTER_URL_RENDERER='cropduster.renderers.ThumborRenderer',
                CROPDUSTER_THUMBOR={
                    'SERVER': 'https://thumb.example.com/',
                }):
            self.assertEqual(check_metadata_only_renderer(), [])


class StubStorage:

    def __init__(self, base_url):
        self.base_url = base_url

    def url(self, name):
        return '%s%s' % (self.base_url, name)


class RefusingStorage:

    def url(self, name):
        raise ValueError('unknown name')


@requires_libthumbor
class TestThumborMediaUrlCheck(test.SimpleTestCase):

    renderer_settings = {
        'CROPDUSTER_URL_RENDERER': 'cropduster.renderers.ThumborRenderer',
        'CROPDUSTER_THUMBOR': {
            'SERVER': 'https://thumb.example.com/',
            'MEDIA_URL': 'https://cdn.example.com/media/',
        },
    }

    def test_matching_prefix_passes(self):
        storage = StubStorage('https://cdn.example.com/media/')
        with mock.patch(
                'cropduster.utils.storage.get_image_storage',
                return_value=storage):
            with test.override_settings(**self.renderer_settings):
                self.assertEqual(check_thumbor_media_url(), [])

    def test_unmatched_prefix_is_w001(self):
        storage = StubStorage('https://bucket.example.com/media/')
        with mock.patch(
                'cropduster.utils.storage.get_image_storage',
                return_value=storage):
            with test.override_settings(**self.renderer_settings):
                errors = check_thumbor_media_url()
        self.assertEqual([error.id for error in errors], ['cropduster.W001'])

    def test_unset_thumbor_media_url_still_checks_other_candidates(self):
        storage = StubStorage('https://bucket.example.com/media/')
        settings = {
            'CROPDUSTER_URL_RENDERER': (
                'cropduster.renderers.ThumborRenderer'),
            'CROPDUSTER_THUMBOR': {
                'SERVER': 'https://thumb.example.com/',
            },
            'MEDIA_URL': '/media/',
        }
        with mock.patch(
                'cropduster.utils.storage.get_image_storage',
                return_value=storage):
            with test.override_settings(**settings):
                errors = check_thumbor_media_url()
        self.assertEqual([error.id for error in errors], ['cropduster.W001'])

    def test_storage_that_refuses_the_probe_passes(self):
        with mock.patch(
                'cropduster.utils.storage.get_image_storage',
                return_value=RefusingStorage()):
            with test.override_settings(**self.renderer_settings):
                self.assertEqual(check_thumbor_media_url(), [])


class TestRendererCheckRegistration(test.SimpleTestCase):

    def test_renderer_checks_are_registered(self):
        names = {
            getattr(check, '__name__', '')
            for check in checks.registry.registry.get_checks()
        }
        self.assertIn('check_url_renderer', names)
        self.assertIn('check_metadata_only_renderer', names)
        self.assertIn('check_thumbor_media_url', names)


class TestApiPermissionCheck(test.SimpleTestCase):

    def test_both_permission_checks_that_ship_can_be_loaded(self):
        self.assertEqual(check_api_permission(), [])
        with test.override_settings(
                CROPDUSTER_API_PERMISSION=(
                    'cropduster.api.permissions.login_required_only')):
            self.assertEqual(check_api_permission(), [])

    def test_unimportable_permission_is_e002(self):
        with test.override_settings(
                CROPDUSTER_API_PERMISSION='not.there.permission'):
            errors = check_api_permission()
        self.assertEqual([error.id for error in errors], ['cropduster.E002'])

    def test_non_callable_permission_is_e002(self):
        with test.override_settings(
                CROPDUSTER_API_PERMISSION='cropduster.api.permissions.__all__'):
            errors = check_api_permission()
        self.assertEqual([error.id for error in errors], ['cropduster.E002'])

    def test_non_string_permission_is_e002(self):
        with test.override_settings(CROPDUSTER_API_PERMISSION=42):
            errors = check_api_permission()
        self.assertEqual([error.id for error in errors], ['cropduster.E002'])

    def test_check_is_registered(self):
        names = {
            getattr(check, '__name__', '')
            for check in checks.registry.registry.get_checks()
        }
        self.assertIn('check_api_permission', names)


class TestDialogModeCheck(test.SimpleTestCase):

    def test_every_dialog_mode_passes(self):
        for mode in ('auto', 'modal', 'window'):
            with self.subTest(mode=mode):
                with test.override_settings(CROPDUSTER_DIALOG_MODE=mode):
                    self.assertEqual(check_dialog_mode(), [])

    def test_unknown_dialog_mode_is_e003(self):
        with test.override_settings(CROPDUSTER_DIALOG_MODE='Modal'):
            errors = check_dialog_mode()

        self.assertEqual([error.id for error in errors], ['cropduster.E003'])
        self.assertIn("'auto'", errors[0].msg)
        self.assertIn("'modal'", errors[0].msg)
        self.assertIn("'window'", errors[0].msg)
        self.assertIn("'Modal'", errors[0].msg)

    def test_check_is_registered(self):
        names = {
            getattr(check, '__name__', '')
            for check in checks.registry.registry.get_checks()
        }
        self.assertIn('check_dialog_mode', names)
