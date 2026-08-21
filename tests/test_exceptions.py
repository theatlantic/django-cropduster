import logging
import os
from io import BytesIO

from django import test
from django.core.exceptions import ImproperlyConfigured
from django.core.files.uploadedfile import SimpleUploadedFile
from django.forms import ValidationError

from cropduster.exceptions import (
    CropDusterConfigurationError, CropDusterException, CropDusterFileException,
    CropDusterFileMissing, ImageTooSmallError, json_error)
from cropduster.resizing import Size
from cropduster.utils import json
from cropduster.views.forms import clean_upload_data

from .helpers import CropdusterTestCaseMediaMixin


class TestNewExceptions(test.SimpleTestCase):

    def test_image_too_small_stores_both_sizes(self):
        error = ImageTooSmallError((600, 480), (100, 50))
        self.assertEqual(error.min_size, (600, 480))
        self.assertEqual(error.actual_size, (100, 50))
        self.assertIsInstance(error, CropDusterException)

    def test_image_too_small_message(self):
        self.assertEqual(str(ImageTooSmallError((600, 480), (100, 50))), (
            "Image must be at least 600x480 "
            "(600 pixels wide and 480 pixels high). "
            "The image you uploaded was 100x50 pixels."))

    def test_file_missing_is_a_file_exception(self):
        self.assertTrue(issubclass(CropDusterFileMissing, CropDusterFileException))

    def test_configuration_error_is_improperly_configured(self):
        self.assertTrue(issubclass(CropDusterConfigurationError, ImproperlyConfigured))


class TestCleanUploadDataMessage(CropdusterTestCaseMediaMixin, test.TestCase):
    """``clean_upload_data()`` raises ``ValidationError`` with
    ``ImageTooSmallError``'s message."""

    def small_upload(self):
        import PIL.Image

        buf = BytesIO()
        PIL.Image.new('RGB', (100, 50)).save(buf, format='JPEG')
        return SimpleUploadedFile('tiny.jpg', buf.getvalue())

    def test_validation_error_uses_the_exception_message(self):
        with self.assertRaises(ValidationError) as ctx:
            clean_upload_data({
                'image': self.small_upload(),
                'upload_to': 'test',
                'sizes': [Size('main', w=600, h=480)],
            })

        self.assertEqual(
            ctx.exception.message_dict['image'],
            [str(ImageTooSmallError((600, 480), (100, 50)))])

    def test_large_enough_upload_is_stored(self):
        with open(os.path.join(self.TEST_IMG_DIR, 'img.jpg'), 'rb') as f:
            upload = SimpleUploadedFile('img.jpg', f.read())

        data = clean_upload_data({
            'image': upload,
            'upload_to': 'test',
            'sizes': [Size('main', w=600, h=480)],
        })
        self.assertTrue(data['md5'])


class TestJsonError(test.SimpleTestCase):
    """Pin the legacy ``json_error()`` response bodies.

    Downstream clients parse the HTTP-200 ``{"error": html}`` envelope, so
    the exact strings matter.
    """

    def setUp(self):
        self.request = test.RequestFactory().post('/cropduster/crop/')

    def test_single_error(self):
        response = json_error(self.request, 'crop', 'cropping image', errors=['boom'])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertEqual(json.loads(response.content), {'error': 'Error cropping image: boom'})

    def test_multiple_errors(self):
        response = json_error(self.request, 'crop', 'cropping image', errors=['a', 'b'])
        self.assertEqual(json.loads(response.content), {'error': (
            'Errors cropping image: <ul>'
            '<li>&nbsp;&nbsp;&nbsp;&bull;&nbsp;a</li>'
            '<li>&nbsp;&nbsp;&nbsp;&bull;&nbsp;b</li>'
            '</ul>')})

    def test_no_errors(self):
        response = json_error(self.request, 'crop', 'cropping image')
        self.assertEqual(json.loads(response.content), {'error': 'An unknown error occurred'})

    def test_logging_does_not_change_the_body(self):
        logging.getLogger('cropduster').addHandler(logging.NullHandler())
        with self.assertLogs('cropduster', level='ERROR') as logs:
            response = json_error(
                self.request, 'crop', 'cropping image', errors=['boom'], log=True)

        self.assertEqual(json.loads(response.content), {'error': 'Error cropping image: boom'})
        self.assertEqual(len(logs.records), 1)
        self.assertEqual(logs.records[0].getMessage(), 'Error cropping image: boom')
