from unittest import mock

from django import test
from django.apps import apps
from django.contrib import admin
from django.core import checks
from django.contrib.contenttypes.admin import GenericInlineModelAdminChecks

from cropduster.checks import (
    check_app_config, check_metadata_only_renderer, check_url_renderer)

from .models import Article


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


class TestMetadataOnlyCheck(test.SimpleTestCase):

    def test_writing_thumbs_passes(self):
        self.assertEqual(check_metadata_only_renderer(), [])

    def test_file_renderer_is_w002_without_derivative_files(self):
        with test.override_settings(CROPDUSTER_CREATE_THUMBS=False):
            errors = check_metadata_only_renderer()
        self.assertEqual([error.id for error in errors], ['cropduster.W002'])


class TestRendererCheckRegistration(test.SimpleTestCase):

    def test_renderer_checks_are_registered(self):
        names = {
            getattr(check, '__name__', '')
            for check in checks.registry.registry.get_checks()
        }
        self.assertIn('check_url_renderer', names)
        self.assertIn('check_metadata_only_renderer', names)
