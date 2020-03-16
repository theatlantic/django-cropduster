from io import open, BytesIO
import os
import shutil
import tempfile

from PIL import Image

from django import test
from django.core.files.storage import default_storage
from django.conf import settings

from .helpers import CropdusterTestCaseMediaMixin


class TestUtilsImage(CropdusterTestCaseMediaMixin, test.TestCase):

    def _get_img(self, filename):
        return Image.open(os.path.join(self.TEST_IMG_DIR, filename))

    def test_that_test_work(self):
        self.assertEqual(True, True)

    def test_get_image_extension(self):
        from ..utils import get_image_extension

        tmp_jpg_bad_ext_pdf = tempfile.NamedTemporaryFile(suffix='.pdf')
        tmp_png_bad_ext_jpg = tempfile.NamedTemporaryFile(suffix='.png')

        with open(os.path.join(self.TEST_IMG_DIR, 'img.jpg'), mode='rb') as f:
            tmp_jpg_bad_ext_pdf.write(f.read())
            tmp_jpg_bad_ext_pdf.seek(0)

        with open(os.path.join(self.TEST_IMG_DIR, 'img.png'), mode='rb') as f:
            tmp_png_bad_ext_jpg.write(f.read())
            tmp_png_bad_ext_jpg.seek(0)

        imgs = [
            (self._get_img('img.jpg'), '.jpg'),
            (self._get_img('img.png'), '.png'),
            (self._get_img('animated.gif'), '.gif'),
            (Image.open(tmp_jpg_bad_ext_pdf.name), '.jpg'),
            (Image.open(tmp_png_bad_ext_jpg.name), '.png'),
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

        path = random = uuid.uuid4().hex
        folder_path = get_upload_foldername('my img.jpg', upload_to=path)
        self.assertEqual(folder_path, "%s/my_img" % (path))
        default_storage.save("%s/original.jpg" % folder_path, BytesIO(b''))
        self.assertEqual(get_upload_foldername('my img.jpg', upload_to=path),
                         os.path.join(path, 'my_img-1'))

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
