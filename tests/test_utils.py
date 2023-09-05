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
        from cropduster.utils import get_image_extension

        with self._get_img('img.jpg') as im:
            assert get_image_extension(im) == ".jpg"
        with self._get_img('img.png') as im:
            assert get_image_extension(im) == ".png"
        with self._get_img('animated.gif') as im:
            assert get_image_extension(im) == ".gif"

        tmp_jpg_bad_ext_pdf = tempfile.NamedTemporaryFile(suffix='.pdf')
        with open(os.path.join(self.TEST_IMG_DIR, 'img.jpg'), mode='rb') as f:
            tmp_jpg_bad_ext_pdf.write(f.read())
            tmp_jpg_bad_ext_pdf.seek(0)
        with Image.open(tmp_jpg_bad_ext_pdf.name) as im:
            assert get_image_extension(im) == ".jpg"
        tmp_jpg_bad_ext_pdf.close()

    def test_is_transparent(self):
        from cropduster.utils import is_transparent
        with self._get_img('transparent.png') as im:
            assert is_transparent(im) is True
        with self._get_img('img.png') as im:
            assert is_transparent(im) is False

    def test_correct_colorspace(self):
        from cropduster.utils import correct_colorspace
        with self._get_img('cmyk.jpg') as img:
            self.assertEqual(img.mode, 'CMYK')
            converted = correct_colorspace(img)
            self.assertEqual(img.mode, 'CMYK')
            self.assertEqual(converted.mode, 'RGB')

    def test_is_animated_gif(self):
        from cropduster.utils import is_animated_gif
        with self._get_img('animated.gif') as yes:
            with self._get_img('img.jpg') as no:
                self.assertTrue(is_animated_gif(yes))
                self.assertFalse(is_animated_gif(no))


class TestUtilsPaths(CropdusterTestCaseMediaMixin, test.TestCase):

    def test_get_upload_foldername(self):
        import uuid
        from cropduster.utils import get_upload_foldername

        path = random = uuid.uuid4().hex
        folder_path = get_upload_foldername('my img.jpg', upload_to=path)
        self.assertEqual(folder_path, "%s/my_img" % (path))
        default_storage.save("%s/original.jpg" % folder_path, BytesIO(b''))
        self.assertEqual(get_upload_foldername('my img.jpg', upload_to=path),
                         os.path.join(path, 'my_img-1'))

    def test_get_min_size(self):
        from cropduster.utils import get_min_size
        from cropduster.resizing import Size

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
