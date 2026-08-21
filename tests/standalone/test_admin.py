from __future__ import absolute_import

import contextlib
import re
import time
from unittest import SkipTest
import os

import django
from django.core.files.storage import default_storage
from django.test import override_settings
from django.test.testcases import LiveServerThread

import PIL.Image
from selenosis import AdminSelenosisTestCase
from selenosis.utils import class_property

from cropduster.models import Image, Thumb
from tests.helpers import CropdusterTestCaseMediaMixin

from .models import StandaloneArticle


class TestStandaloneAdmin(CropdusterTestCaseMediaMixin, AdminSelenosisTestCase):

    server_thread_class = LiveServerThread
    root_urlconf = 'tests.urls'

    @class_property
    def available_apps(cls):
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
        if cls.has_grappelli:
            apps.insert(0, 'grappelli')
        return apps

    def _instance_pre_setup(self):
        super(TestStandaloneAdmin, self)._instance_pre_setup()
        self.ckeditor_override = override_settings(
            CKEDITOR_UPLOAD_PATH="%s/files/" % self.temp_media_root)
        self.ckeditor_override.enable()

    def _post_teardown(self):
        super(TestStandaloneAdmin, self)._post_teardown()
        self.ckeditor_override.disable()

    def setUp(self):
        if self.has_grappelli and django.VERSION >= (3, 2):
            raise SkipTest("django-ckeditor is not yet compatible with django 3.2+ and grappelli")
        super(TestStandaloneAdmin, self).setUp()
        self.is_s3 = os.environ.get('S3') == '1'

    @contextlib.contextmanager
    def switch_to_ckeditor_iframe(self):
        """Run the block in the document that owns the dialog shadow root."""
        with self.visible_selector('.cke_editor_cropduster_content_dialog iframe') as iframe:
            self.wait_until(
                lambda driver: iframe.get_attribute('src') not in (
                    None, '', 'about:blank'),
                message=(
                    "Timeout waiting for the cropduster iframe to be pointed "
                    "at the dialog"))
            self.selenium.switch_to.frame(iframe)
            try:
                yield iframe
            finally:
                self.selenium.switch_to.parent_frame()

    @contextlib.contextmanager
    def open_cropduster_ckeditor_dialog(self):
        with self.clickable_selector('.cke_button__cropduster_icon') as el:
            el.click()

        with self.switch_to_ckeditor_iframe():
            self.wait_for_dialog()
            self.dialog_find('#id_image', visible=False)
            yield

    def toggle_caption_checkbox(self):
        caption_checkbox_xpath = '//input[following-sibling::label[text()="Captioned image"]]'
        with self.clickable_xpath(caption_checkbox_xpath) as checkbox:
            checkbox.click()
            self.wait_until(
                lambda driver: checkbox.is_selected(),
                message="Timeout waiting for the caption checkbox to be checked")

    def cropduster_ckeditor_ok(self):
        from selenium.webdriver.common.by import By

        with self.clickable_selector('.cke_dialog_ui_button_ok') as ok:
            ok.click()
        self.wait_until(
            lambda driver: not any(
                element.is_displayed() for element in driver.find_elements(
                    By.CSS_SELECTOR, '.cke_editor_cropduster_content_dialog')),
            timeout=30 if self.is_s3 else None,
            message="Timeout waiting for the cropduster CKEditor dialog to close")

    def test_basic_usage(self):
        self.load_admin(StandaloneArticle)

        with self.open_cropduster_ckeditor_dialog():
            self.dialog_send_keys(
                '#id_image', os.path.join(self.TEST_IMG_DIR, 'img.png'))
            self.dialog_click('#upload-button')
            self.dialog_find('#id_size-width')

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
            """
            <figure>
                <img alt="" width="672" height="798" src="%s" />
                <figcaption class="caption">Caption</figcaption>
            </figure>
            <p>&nbsp;</p>
            """ % image_url)

    def test_ok_button_does_not_close_before_crop(self):
        self.load_admin(StandaloneArticle)

        with self.open_cropduster_ckeditor_dialog():
            self.assertFalse(self.dialog_can_commit())

        with self.clickable_selector('.cke_dialog_ui_button_ok') as ok:
            ok.click()

        with self.visible_selector('.cke_editor_cropduster_content_dialog iframe'):
            pass

        with self.clickable_selector('.cke_dialog_ui_button_cancel') as cancel:
            cancel.click()

    def test_ok_button_drives_the_crop(self):
        self.load_admin(StandaloneArticle)

        with self.open_cropduster_ckeditor_dialog():
            self.dialog_send_keys(
                '#id_image', os.path.join(self.TEST_IMG_DIR, 'img.png'))
            self.dialog_click('#upload-button')
            self.dialog_find('#id_size-width')
            self.assertTrue(self.dialog_can_commit())

        self.assertEqual(Thumb.objects.count(), 0)
        self.cropduster_ckeditor_ok()
        self.assertEqual(Thumb.objects.count(), 1)
        content_html = self.selenium.execute_script('return $("#id_content").val()')
        self.assertIn(Thumb.objects.get().name, content_html)

    def test_iframe_grows_to_fit_the_crop_box(self):
        """
        The dialog document is taller than the iframe's 650x400 markup once
        an image is loaded. The CKEditor dialog measures the document and
        resizes the iframe, so the crop box and its south drag handles must
        end up fully inside the iframe's viewport instead of clipped.
        """
        self.load_admin(StandaloneArticle)

        with self.open_cropduster_ckeditor_dialog():
            self.dialog_send_keys(
                '#id_image', os.path.join(self.TEST_IMG_DIR, 'img.png'))
            self.dialog_click('#upload-button')
            self.dialog_find('#cropbox')

            self.wait_until(
                lambda driver: driver.execute_script("""
                    var doc = document.documentElement;
                    return (window.innerHeight >= doc.scrollHeight
                            && window.innerWidth >= doc.scrollWidth);
                """),
                message=(
                    "Timeout waiting for the iframe to grow around the "
                    "dialog document"))

            rect = self.dialog_rect('#cropbox')
            viewport = self.selenium.execute_script(
                "return {width: window.innerWidth, height: window.innerHeight};")
            self.assertGreater(rect['height'], 0)
            self.assertLessEqual(rect['y'] + rect['height'], viewport['height'])
            self.assertLessEqual(rect['x'] + rect['width'], viewport['width'])

        iframe_height = self.selenium.execute_script("""
            return document.querySelector(
                '.cke_editor_cropduster_content_dialog iframe'
            ).getBoundingClientRect().height;
        """)
        self.assertGreater(
            iframe_height, 400,
            "The iframe should have grown beyond the 400px in its markup")

    def test_dialog_change_width(self):
        """
        Test that changing the width in the cropduster CKEDITOR dialog produces
        an image and html with the correct dimensions
        """
        self.load_admin(StandaloneArticle)

        with self.open_cropduster_ckeditor_dialog():
            self.dialog_send_keys(
                '#id_image', os.path.join(self.TEST_IMG_DIR, 'img.png'))
            self.dialog_click('#upload-button')
            self.dialog_send_keys('#id_size-width', 300)
            self.wait_until(
                lambda driver: self.dialog_value('#id_size-width') == '300',
                message="Timeout waiting for the width field to take the new value")

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
            """
            <figure>
                <img alt="" width="300" height="356" src="%s" />
                <figcaption class="caption">Caption</figcaption>
            </figure>
            <p>&nbsp;</p>
            """ % image_url)
