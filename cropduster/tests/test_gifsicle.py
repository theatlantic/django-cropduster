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

    def test_gifsicle_init(self):
        from ..utils.gifsicle import GifsicleImage
        pil_img = self._get_img('animated.gif')
        gif = GifsicleImage(pil_img)
        self.assertTrue(len(str(gif.src_bytes)) > 0)

    def test_gifsicle_duration(self):
        from ..utils.gifsicle import GifsicleImage
        pil_img = self._get_img('animated-duration.gif')
        durations = [i.info['duration'] for i in ImageSequence.Iterator(pil_img)]
        gif = GifsicleImage(pil_img)
        buffer = BytesIO()
        gif.save(buffer, format=pil_img.format)
        out_im = Image.open(buffer)
        out_durations = [f.info['duration'] for f in ImageSequence.Iterator(out_im)]
        self.assertEqual(out_durations, durations)

    def test_is_animated_gif(self):
        from ..utils import is_animated_gif
        yes = self._get_img('animated.gif')
        no = self._get_img('img.jpg')
        self.assertTrue(is_animated_gif(yes))
        self.assertFalse(is_animated_gif(no))

