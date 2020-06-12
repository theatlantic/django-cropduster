from __future__ import absolute_import

import contextlib
import re
import time
from unittest import SkipTest
import os

import django
from django.core.files.storage import default_storage
from django.test import override_settings

import PIL.Image
from selenosis import AdminSelenosisTestCase

from cropduster.models import Image, Thumb
from tests.helpers import CropdusterTestCaseMediaMixin

from .models import Article


class TestStandaloneAdmin(CropdusterTestCaseMediaMixin, AdminSelenosisTestCase):

    root_urlconf = 'tests.urls'

    @property
    def available_apps(self):
        apps = [
            'django.contrib.auth',
            'django.contrib.contenttypes',
            'django.contrib.messages',
            'django.contrib.sessions',
            'django.contrib.sites',
            'django.contrib.staticfiles',
            'django.contrib.admin',
            'generic_plus',
            'cropduster',
            'cropduster.standalone',
            'tests',
            'tests.standalone',
            'ckeditor',
            'selenosis',
        ]
        if self.has_grappelli:
            apps.insert(0, 'grappelli')
        return apps

    def _pre_setup(self):
        super(TestStandaloneAdmin, self)._pre_setup()
        self.ckeditor_override = override_settings(
            CKEDITOR_UPLOAD_PATH="%s/files/" % self.temp_media_root)
        self.ckeditor_override.enable()

    def _post_teardown(self):
        super(TestStandaloneAdmin, self)._post_teardown()
        self.ckeditor_override.disable()

    def setUp(self):
        if django.VERSION >= (2, 1):
            raise SkipTest("django-ckeditor not compatible with this version of Django")
        super(TestStandaloneAdmin, self).setUp()
        self.is_s3 = os.environ.get('S3') == '1'

    @contextlib.contextmanager
    def switch_to_ckeditor_iframe(self):
        with self.visible_selector('.cke_editor_cropduster_content_dialog iframe') as iframe:
            time.sleep(1)
            self.selenium.switch_to.frame(iframe)
            yield iframe
            self.selenium.switch_to.parent_frame()

    @contextlib.contextmanager
    def open_cropduster_ckeditor_dialog(self):
        with self.clickable_selector('.cke_button__cropduster_icon') as el:
            el.click()

        with self.switch_to_ckeditor_iframe():
            time.sleep(1)
            with self.visible_selector('#id_image'):
                yield

    def toggle_caption_checkbox(self):
        caption_checkbox_xpath = '//input[following-sibling::label[text()="Captioned image"]]'
        with self.clickable_xpath(caption_checkbox_xpath) as checkbox:
            checkbox.click()
        time.sleep(0.2)

    def cropduster_ckeditor_ok(self):
        with self.clickable_selector('.cke_dialog_ui_button_ok') as ok:
            ok.click()
        time.sleep(2 if self.is_s3 else 0.2)

    def test_basic_usage(self):
        self.load_admin(Article)

        with self.open_cropduster_ckeditor_dialog():
            with self.visible_selector('#id_image') as el:
                el.send_keys(os.path.join(self.TEST_IMG_DIR, 'img.png'))
            with self.clickable_selector('#upload-button') as el:
                el.click()
            self.wait_until_visible_selector('#id_size-width')

        self.toggle_caption_checkbox()
        self.cropduster_ckeditor_ok()

        if self.is_s3:
            time.sleep(5)

        content_html = self.selenium.execute_script('return $("#id_content").val()')

        img_src_matches = re.search(r' src="([^"]+)"', content_html)
        self.assertIsNotNone(img_src_matches, "Image not found in content: %s" % content_html)
        image_url = img_src_matches.group(1)
        image_hash = re.search(r'img/([0-9a-f]+)\.png', image_url).group(1)

        try:
            image = Image.objects.get(image='ckeditor/img/original.png')
        except Image.DoesNotExist:
            raise AssertionError("Image not found in database")

        try:
            thumb = Thumb.objects.get(name=image_hash, image=image)
        except Thumb.DoesNotExist:
            raise AssertionError("Thumb not found in database")

        self.assertEqual(
            list(Thumb.objects.all()), [thumb],
            "Exactly one Thumb object should have been created")

        self.assertHTMLEqual(
            content_html,
            u"""
            <figure>
                <img alt="" width="672" height="798" src="%s" />
                <figcaption class="caption">Caption</figcaption>
            </figure>
            <p>&nbsp;</p>
            """ % image_url)

    def test_dialog_change_width(self):
        """
        Test that changing the width in the cropduster CKEDITOR dialog produces
        an image and html with the correct dimensions
        """
        self.load_admin(Article)

        with self.open_cropduster_ckeditor_dialog():
            with self.visible_selector('#id_image') as el:
                el.send_keys(os.path.join(self.TEST_IMG_DIR, 'img.png'))
            with self.clickable_selector('#upload-button') as el:
                el.click()
            time.sleep(1)
            with self.clickable_selector('#id_size-width') as el:
                el.send_keys(300)

        self.toggle_caption_checkbox()
        self.cropduster_ckeditor_ok()

        if self.is_s3:
            time.sleep(5)

        content_html = self.selenium.execute_script('return $("#id_content").val()')

        img_src_matches = re.search(r' src="([^"]+)"', content_html)
        self.assertIsNotNone(img_src_matches, "Image not found in content: %s" % content_html)
        image_url = img_src_matches.group(1)
        image_hash = re.search(r'img/([0-9a-f]+)\.png', image_url).group(1)

        try:
            image = Image.objects.get(image='ckeditor/img/original.png')
        except Image.DoesNotExist:
            raise AssertionError("Image not found in database")

        try:
            thumb = Thumb.objects.get(name=image_hash, image=image)
        except Thumb.DoesNotExist:
            raise AssertionError("Thumb not found in database")

        self.assertEqual(
            list(Thumb.objects.all()), [thumb],
            "Exactly one Thumb object should have been created")

        with default_storage.open("ckeditor/img/%s.png" % image_hash, mode='rb') as f:
            self.assertEqual(PIL.Image.open(f).size, (300, 356))

        self.assertHTMLEqual(
            content_html,
            u"""
            <figure>
                <img alt="" width="300" height="356" src="%s" />
                <figcaption class="caption">Caption</figcaption>
            </figure>
            <p>&nbsp;</p>
            """ % image_url)
