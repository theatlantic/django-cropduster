"""
Test the standalone dialog's ``callback_fn`` integration without CKEditor.

When ``callback_fn`` is supplied, the dialog calls that named global on
``window.opener`` or ``window.parent`` with the callback name and legacy crop
response. This is the only completion path that does not call
``CropDuster.complete()``.

The test page embeds the dialog in an iframe and implements the callback
directly. It calls ``CropDusterDialog.commit()`` in the same way as CKEditor's
OK button because standalone mode does not display its own crop button.
"""

from __future__ import absolute_import

import os
from urllib.parse import urlencode

from django.test.testcases import LiveServerThread
from django.urls import reverse

from selenosis import AdminSelenosisTestCase
from selenosis.utils import class_property

from cropduster.models import Image, Thumb
from tests.helpers import CropdusterTestCaseMediaMixin


class TestCallbackFn(CropdusterTestCaseMediaMixin, AdminSelenosisTestCase):

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

    def load_callback_host(self, **params):
        """Open the host page with the dialog framed inside it."""
        params.setdefault('callback_fn', 'myCb')
        params.setdefault('upload_to', 'img/callback/%Y/%m')
        dialog = '%s?%s' % (reverse('cropduster-standalone'), urlencode(params))
        url = '%s%s?%s' % (
            self.live_server_url, reverse('test-callback-host'),
            urlencode({'dialog': dialog}))
        self.selenium.get(url)
        self.wait_page_loaded()

    @property
    def callback_calls(self):
        return self.selenium.execute_script(
            "return window.cropdusterCallbackCalls;")

    def enter_dialog_frame(self):
        from selenium.webdriver.common.by import By

        frame = self.selenium.find_element(By.ID, 'dialog-frame')
        self.selenium.switch_to.frame(frame)
        self.wait_for_dialog()

    def test_callback_receives_the_legacy_payload(self):
        self.load_callback_host()

        self.enter_dialog_frame()
        self.dialog_send_keys('#id_image', os.path.join(self.TEST_IMG_DIR, 'img.png'))
        self.dialog_click('#upload-button')
        self.dialog_commit()
        self.selenium.switch_to.default_content()

        self.wait_until(
            lambda d: len(self.callback_calls) == 1,
            message="Timeout waiting for the dialog to call back")

        (name, payload), = self.callback_calls
        # The callback name is the first argument so one handler can identify
        # which of several dialogs called it.
        self.assertEqual(name, 'myCb')

        image = Image.objects.get()
        thumb = Thumb.objects.get()

        self.assertEqual(payload['initial'], True)
        self.assertEqual(payload['crop']['image_id'], image.pk)
        self.assertEqual(payload['crop']['orig_image'], image.name)
        self.assertEqual(payload['crop']['standalone'], True)
        self.assertEqual(set(payload['crop']['thumbs']), {thumb.name})

        # CKEditor reads these values to size the inserted image and set its
        # source.
        self.assertEqual(len(payload['thumbs']), 1)
        self.assertEqual(payload['thumbs'][0]['id'], thumb.pk)
        self.assertEqual(payload['thumbs'][0]['name'], thumb.name)
        self.assertEqual(payload['thumbs'][0]['width'], thumb.width)
        self.assertEqual(payload['thumbs'][0]['height'], thumb.height)
        self.assertIn(thumb.name, payload['thumbs'][0]['url'])

    def test_callback_honours_max_w(self):
        """``max_w`` is how the editor's layout width reaches the crop."""
        self.load_callback_host(max_w=300)

        self.enter_dialog_frame()
        self.dialog_send_keys('#id_image', os.path.join(self.TEST_IMG_DIR, 'img.png'))
        self.dialog_click('#upload-button')
        self.dialog_commit()
        self.selenium.switch_to.default_content()

        self.wait_until(
            lambda d: len(self.callback_calls) == 1,
            message="Timeout waiting for the dialog to call back")

        payload = self.callback_calls[0][1]
        self.assertEqual(payload['thumbs'][0]['width'], 300)
