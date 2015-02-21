import os
import shutil
from PIL import Image

from django import test
from django.conf import settings

from .helpers import CropdusterTestCaseMediaMixin


class TestUtilsImage(CropdusterTestCaseMediaMixin, test.TestCase):

    def _get_img(self, filename):
        return Image.open(os.path.join(self.TEST_IMG_DIR, filename))

    def test_that_test_work(self):
        self.assertEqual(True, True)

    def test_get_image_extension(self):
        from ..utils import get_image_extension
        shutil.copyfile(
            os.path.join(self.TEST_IMG_DIR, 'img.jpg'),
            os.path.join(self.TEST_IMG_DIR, 'jpg_bad_ext.pdf'))

        shutil.copyfile(
            os.path.join(self.TEST_IMG_DIR, 'img.png'),
            os.path.join(self.TEST_IMG_DIR, 'png_bad_ext.jpg'))

        imgs = [
            (self._get_img('img.jpg'), '.jpg'),
            (self._get_img('img.png'), '.png'),
            (self._get_img('animated.gif'), '.gif'),
            (self._get_img('jpg_bad_ext.pdf'), '.jpg'),
            (self._get_img('png_bad_ext.jpg'), '.png'),
        ]
        for img, ext in imgs:
            self.assertEqual(get_image_extension(img), ext)

    def test_is_transparent(self):
        from ..utils import is_transparent
        yes = self._get_img('transparent.png')
        no = self._get_img('img.png')

        self.assertTrue(is_transparent(yes))
        self.assertFalse(is_transparent(no))

    def test_correct_colorspace(self):
        from ..utils import correct_colorspace
        img = self._get_img('cmyk.jpg')
        self.assertEqual(img.mode, 'CMYK')
        converted = correct_colorspace(img)
        self.assertEqual(img.mode, 'CMYK')
        self.assertEqual(converted.mode, 'RGB')

    def test_is_animated_gif(self):
        from ..utils import is_animated_gif
        yes = self._get_img('animated.gif')
        no = self._get_img('img.jpg')
        self.assertTrue(is_animated_gif(yes))
        self.assertFalse(is_animated_gif(no))


class TestUtilsPaths(CropdusterTestCaseMediaMixin, test.TestCase):

    def test_get_upload_foldername(self):
        import uuid
        from ..utils import get_upload_foldername

        random = uuid.uuid4().hex
        path = os.path.join(settings.MEDIA_ROOT, random)
        self.assertEqual(get_upload_foldername('my img.jpg', upload_to=random),
                         os.path.join(path, 'my_img'))
        self.assertEqual(get_upload_foldername('my img.jpg', upload_to=random),
                         os.path.join(path, 'my_img-1'))
        shutil.rmtree(path)

    def test_get_min_size(self):
        from ..utils import get_min_size
        from ..resizing import Size

        sizes = [
            Size('a', w=200, h=200),
            Size('b', w=100, h=300),
            Size('c', w=20, h=20)
        ]
        self.assertEqual(get_min_size(sizes), (200, 300))

        sizes = [
            Size('a', min_w=200, min_h=200, max_h=500),
            Size('b', min_w=100, min_h=300),
            Size('c', w=20, h=20)
        ]
        self.assertEqual(get_min_size(sizes), (200, 300))

    def test_get_media_path(self):
        from generic_plus.utils import get_media_path

        img_name = '/test/some-test-image.jpg'
        from_url = settings.MEDIA_URL + img_name
        to_url = settings.MEDIA_ROOT + img_name
        self.assertEqual(get_media_path(from_url), to_url)
