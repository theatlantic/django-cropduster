"""Check that Cropduster reads every image file from ``Image.image.storage``.

These tests replace that storage with one that shares no files with
``default_storage``. A lookup that checks one backend and reads from the other
therefore fails immediately.
"""

import os
import shutil
import tempfile
from unittest import mock

from django import test
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage, default_storage
from django.core.files.uploadedfile import SimpleUploadedFile

from cropduster.files import ImageFile, VirtualFieldFile
from cropduster.models import Image
from cropduster.standalone.metadata import MetadataImageFile
from cropduster.views.forms import clean_upload_data


class CustomImageStorageTestCase(test.SimpleTestCase):
    """Point ``Image.image`` at storage isolated from ``default_storage``."""

    def setUp(self):
        super(CustomImageStorageTestCase, self).setUp()
        tmpdir = tempfile.mkdtemp(prefix='TEST_IMAGE_STORAGE_')
        self.addCleanup(shutil.rmtree, tmpdir)
        self.storage = FileSystemStorage(location=tmpdir)

        source = os.path.join(os.path.dirname(__file__), 'data', 'img.jpg')
        with open(source, 'rb') as f:
            self.storage.save('img/original.jpg', ContentFile(f.read()))

        patched = mock.patch.object(Image._meta.get_field('image'), 'storage', self.storage)
        patched.start()
        self.addCleanup(patched.stop)


class TestVirtualFieldFileStorage(CustomImageStorageTestCase):

    def test_defaults_to_the_image_field_storage(self):
        self.assertIs(VirtualFieldFile('img/original.jpg').storage, self.storage)

    def test_an_explicit_storage_still_wins(self):
        self.assertIs(VirtualFieldFile('img/original.jpg', storage=default_storage).storage,
                      default_storage)

    def test_it_reads_the_file(self):
        with VirtualFieldFile('img/original.jpg') as f:
            f.open()
            self.assertTrue(f.read())


class TestImageFileStorage(CustomImageStorageTestCase):

    def test_uploads_are_written_to_the_image_storage(self):
        source = os.path.join(os.path.dirname(__file__), 'data', 'img.jpg')
        with open(source, 'rb') as source_file:
            upload = SimpleUploadedFile('upload.jpg', source_file.read())

        data = clean_upload_data({
            'image': upload,
            'upload_to': 'custom-storage',
        })

        self.assertTrue(self.storage.exists(data['image'].name))
        self.assertFalse(default_storage.exists(data['image'].name))

    def test_the_existence_probe_and_the_read_agree(self):
        image_file = ImageFile('img/original.jpg')

        self.assertTrue(image_file)
        self.assertIs(image_file.storage, self.storage)
        # ``dimensions`` returns (0, 0) after a read error, so the expected
        # dimensions confirm that the file was read from the custom storage.
        self.assertEqual(image_file.dimensions, (674, 800))

    def test_file_size_uses_the_image_storage(self):
        image = Image(image='img/original.jpg')
        self.assertGreater(image.get_image_filesize(), 0)

    def test_the_preview_lands_in_the_same_storage(self):
        preview = ImageFile('img/original.jpg').preview_image

        self.assertTrue(self.storage.exists(preview.name))
        self.assertFalse(default_storage.exists(preview.name))


class TestMetadataImageFileStorage(CustomImageStorageTestCase):

    def test_the_metadata_read_uses_the_image_storage(self):
        metadata_file = MetadataImageFile('img/original.jpg')

        self.assertIs(metadata_file.metadata.storage, self.storage)
