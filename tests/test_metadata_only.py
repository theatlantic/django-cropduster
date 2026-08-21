"""Check crop geometry calculated without an image file.

When ``CROPDUSTER_CREATE_THUMBS = False``, a URL renderer may create a crop on
demand without a stored rendition. Its crop boxes must still match those
calculated from the image file.
"""

from io import BytesIO
import os

import PIL.Image

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import SimpleTestCase, TestCase

from cropduster.exceptions import CropDusterFileMissing
from cropduster.models import Thumb
from cropduster.resizing import Box, Crop, Size, image_size

from .helpers import CropdusterTestCaseMediaMixin


SIZE = Size('main', w=220, h=180)


class TestImageSize(CropdusterTestCaseMediaMixin, TestCase):

    def setUp(self):
        super(TestImageSize, self).setUp()
        self.name = 'img.jpg'
        with open(os.path.join(self.TEST_IMG_DIR, 'img.jpg'), mode='rb') as f:
            self.contents = f.read()
        default_storage.save(self.name, ContentFile(self.contents))

    def test_a_pil_image(self):
        self.assertEqual(image_size(PIL.Image.open(BytesIO(self.contents))), (674, 800))

    def test_a_storage_path(self):
        self.assertEqual(image_size(self.name), (674, 800))

    def test_a_pair(self):
        self.assertEqual(image_size((674, 800)), (674, 800))
        self.assertEqual(image_size([674, 800]), (674, 800))

    def test_a_django_file(self):
        """``image_size`` reads ``width`` and ``height``, not a Django file's
        byte-count ``size``."""
        from cropduster.files import VirtualFieldFile

        self.assertEqual(image_size(VirtualFieldFile(self.name)), (674, 800))

    def test_anything_with_a_size(self):
        class Sized(object):
            size = (12, 34)

        self.assertEqual(image_size(Sized()), (12, 34))

    def test_a_pair_of_the_wrong_length(self):
        with self.assertRaises(ValueError):
            image_size((1, 2, 3))

    def test_something_that_is_not_an_image(self):
        with self.assertRaises(TypeError):
            image_size(object())


class TestGeometryWithoutAFile(CropdusterTestCaseMediaMixin, TestCase):

    def setUp(self):
        super(TestGeometryWithoutAFile, self).setUp()
        with open(os.path.join(self.TEST_IMG_DIR, 'img.jpg'), mode='rb') as f:
            self.pil_image = PIL.Image.open(BytesIO(f.read()))
        self.dimensions = self.pil_image.size

    def test_fit_image_agrees_with_the_file_backed_path(self):
        self.assertEqual(
            SIZE.fit_image(self.dimensions).box, SIZE.fit_image(self.pil_image).box)

    def test_fit_to_crop_agrees_with_the_file_backed_path(self):
        thumb = Thumb(name='main', crop_x=0, crop_y=0, crop_w=674, crop_h=800)

        self.assertEqual(
            SIZE.fit_to_crop(thumb, original_image=self.dimensions).box,
            SIZE.fit_to_crop(thumb, original_image=self.pil_image).box)

    def test_thumb_crop_agrees_with_the_file_backed_path(self):
        def crop_for(original_image):
            thumb = Thumb(name='thumb', crop_x=0, crop_y=0, crop_w=674, crop_h=800)
            thumb.reference_thumb = Thumb(
                name='main', crop_x=0, crop_y=0, crop_w=674, crop_h=800)
            return thumb.crop(original_image, Size('thumb', w=110, h=90)), thumb

        from_dimensions, thumb_a = crop_for(self.dimensions)
        from_file, thumb_b = crop_for(self.pil_image)

        self.assertEqual(from_dimensions.box, from_file.box)
        self.assertEqual((thumb_a.width, thumb_a.height), (thumb_b.width, thumb_b.height))

    def test_the_default_crop_geometry_is_unchanged(self):
        """The ``main`` box for the 674x800 test image stays (0, 124, 674, 675)."""
        self.assertEqual(SIZE.fit_image((674, 800)).box, Box(0, 124, 674, 675))

    def test_a_crop_built_from_dimensions_has_no_pixels_to_write(self):
        crop = Crop(Box(0, 0, 220, 180), (674, 800))

        with self.assertRaises(CropDusterFileMissing):
            crop.create_image('nope.jpg', width=220, height=180)


class TestCropSource(SimpleTestCase):

    def test_bounds_come_from_the_dimensions(self):
        crop = Crop(Box(10, 10, 30, 30), (674, 800))

        self.assertIsNone(crop.image)
        self.assertEqual(crop.size, (674, 800))
        self.assertEqual(crop.bounds, Box(0, 0, 674, 800))

    def test_best_fit_keeps_the_dimensions(self):
        crop = Crop(Box(0, 0, 674, 800), (674, 800)).best_fit(
            w=220, h=180, min_w=220, min_h=180)

        self.assertIsNone(crop.image)
        self.assertEqual(crop.bounds, Box(0, 0, 674, 800))
