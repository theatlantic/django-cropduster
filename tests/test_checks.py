from unittest import mock

from django import test
from django.apps import apps
from django.contrib import admin
from django.contrib.contenttypes.admin import GenericInlineModelAdminChecks

from cropduster.checks import check_app_config

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
