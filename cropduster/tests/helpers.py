from io import open
import tempfile
import os
import shutil
import uuid

import PIL.Image

from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.test import override_settings

from .utils import repr_rgb


PATH = os.path.split(__file__)[0]
ORIG_IMG_PATH = os.path.join(PATH, 'data')


class CropdusterTestCaseMediaMixin(object):

    def _pre_setup(self):
        super(CropdusterTestCaseMediaMixin, self)._pre_setup()
        self.temp_media_root = tempfile.mkdtemp(prefix='TEST_MEDIA_ROOT_')
        self.override = override_settings(MEDIA_ROOT=self.temp_media_root)
        self.override.enable()

    def _post_teardown(self):
        if hasattr(default_storage, 'bucket'):
            default_storage.bucket.objects.filter(Prefix=default_storage.location).delete()
        shutil.rmtree(self.temp_media_root)
        self.override.disable()
        super(CropdusterTestCaseMediaMixin, self)._post_teardown()

    def setUp(self):
        super(CropdusterTestCaseMediaMixin, self).setUp()

        random = uuid.uuid4().hex
        self.TEST_IMG_DIR = ORIG_IMG_PATH
        self.TEST_IMG_DIR_RELATIVE = os.path.join(random, 'data')

    def assertImageColorEqual(self, element, image):
        self.selenium.execute_script('arguments[0].scrollIntoView()', element)
        scroll_top = -1 * self.selenium.execute_script(
            'return document.body.getBoundingClientRect().top')
        tmp_file = tempfile.NamedTemporaryFile(suffix='.png')
        if not self.selenium.save_screenshot(tmp_file.name):
            raise Exception("Failed to save screenshot")
        pixel_density = self.selenium.execute_script('return window.devicePixelRatio') or 1
        im1 = PIL.Image.open(tmp_file.name).convert('RGB')
        x1 = int(round(element.location['x'] + (element.size['width'] // 2.0)))
        y1 = int(round(element.location['y'] - scroll_top + (element.size['height'] // 2.0)))
        rgb1 = im1.getpixel((x1 * pixel_density, y1 * pixel_density))
        im2 = PIL.Image.open(os.path.join(os.path.dirname(__file__), 'data', image)).convert('RGB')
        w, h = im2.size
        x2, y2 = int(round(w // 2.0)), int(round(h // 2.0))
        rgb2 = im2.getpixel((x2, y2))
        if rgb1 != rgb2:
            msg = "Colors differ: %s != %s" % (repr_rgb(rgb1), repr_rgb(rgb2))
            self.fail(msg)

    def create_unique_image(self, image):
        image_uuid = uuid.uuid4().hex

        ext = os.path.splitext(image)[1]
        image_name = os.path.join(
            self.TEST_IMG_DIR_RELATIVE, image_uuid, "original%s" % ext)

        with open("%s/%s" % (ORIG_IMG_PATH, image), mode='rb') as f:
            default_storage.save(image_name, ContentFile(f.read()))

        return image_name
