from io import open, BytesIO
import os
import shutil
import tempfile

from PIL import Image, ImageSequence
from io import BytesIO

from django import test
from django.core.files.storage import default_storage
from django.conf import settings

from .helpers import CropdusterTestCaseMediaMixin


class TestUtilsImage(CropdusterTestCaseMediaMixin, test.TestCase):

    def _get_img(self, filename):
        return Image.open(os.path.join(self.TEST_IMG_DIR, filename))

    def test_is_animated_gif(self):
        from cropduster.utils import is_animated_gif
        with self._get_img('animated.gif') as yes:
            with self._get_img('img.jpg') as no:
                self.assertTrue(is_animated_gif(yes))
                self.assertFalse(is_animated_gif(no))

