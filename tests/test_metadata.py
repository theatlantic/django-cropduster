import os
import shutil
import tempfile
from io import BytesIO

import PIL.Image

from django import test
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage, Storage

from cropduster.resizing import Box, Crop, Size
from cropduster.standalone.metadata import MetadataDict, get_xmp_from_storage


class NoPathStorage(Storage):
    """Provide storage whose files are available only through ``open()``.

    Object storage backends such as S3 do not implement ``Storage.path()``,
    so exempi cannot read their files by path.
    """

    def __init__(self, delegate):
        self.delegate = delegate

    def path(self, name):
        raise NotImplementedError("This backend doesn't support absolute paths.")

    def _open(self, name, mode='rb'):
        return self.delegate.open(name, mode)

    def exists(self, name):
        return self.delegate.exists(name)


class MetadataTestCase(test.TestCase):

    def setUp(self):
        super(MetadataTestCase, self).setUp()
        self.tmpdir = tempfile.mkdtemp(prefix='TEST_METADATA_')
        self.addCleanup(shutil.rmtree, self.tmpdir)
        self.storage = FileSystemStorage(location=self.tmpdir)

        source = os.path.join(os.path.dirname(__file__), 'data', 'img.jpg')
        with open(source, 'rb') as f:
            self.storage.save('original.jpg', ContentFile(f.read()))

        with self.storage.open('original.jpg', 'rb') as f:
            pil_image = PIL.Image.open(BytesIO(f.read()))
            pil_image.filename = 'original.jpg'

        crop = Crop(Box(0, 0, 200, 100), pil_image, storage=self.storage)
        crop.create_image('crop.jpg', width=200, height=100)
        crop.add_xmp_to_crop('crop.jpg', Size('crop', w=200, h=100))


class TestMetadataDictStorage(MetadataTestCase):

    def test_reads_through_a_local_path(self):
        metadata = MetadataDict('crop.jpg', storage=self.storage)
        self.assertEqual(metadata.file_path, self.storage.path('crop.jpg'))
        self.assertIsNone(metadata.tmp_file)
        self.assertEqual(metadata.crop_size.w, 200)

    def test_falls_back_to_a_temp_file_without_one(self):
        storage = NoPathStorage(self.storage)
        metadata = MetadataDict('crop.jpg', storage=storage)
        self.assertIsNotNone(metadata.tmp_file)
        self.assertEqual(metadata.file_path, metadata.tmp_file.name)
        self.assertEqual(metadata.crop_size.w, 200)

    def test_crop_thumb_survives_the_temp_file_path(self):
        storage = NoPathStorage(self.storage)
        thumb = MetadataDict('crop.jpg', storage=storage).crop_thumb
        # XMP stores the crop region as a normalized fraction.
        self.assertAlmostEqual(thumb.crop_w, 200, delta=1)
        self.assertAlmostEqual(thumb.crop_h, 100, delta=1)
        self.assertEqual((thumb.width, thumb.height), (200, 100))


class TestMetadataDictFromString(MetadataTestCase):

    def test_parses_a_raw_xmp_packet(self):
        xmp = get_xmp_from_storage('crop.jpg', storage=self.storage)
        from_file = MetadataDict('crop.jpg', storage=self.storage)
        from_string = MetadataDict.from_string(str(xmp))

        self.assertEqual(from_string['Regions'], from_file['Regions'])
        self.assertEqual(from_string['md5'], from_file['md5'])
        self.assertEqual(
            from_string['size']['json'].__serialize__(),
            from_file['size']['json'].__serialize__())
        self.assertEqual(from_string.crop_size.w, 200)

    def test_crop_thumb_needs_a_file(self):
        xmp = get_xmp_from_storage('crop.jpg', storage=self.storage)
        self.assertIsNone(MetadataDict.from_string(str(xmp)).crop_thumb)
