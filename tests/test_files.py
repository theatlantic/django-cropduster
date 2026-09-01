from unittest import mock

from django import test

from cropduster.files import ImageFile

from .helpers import CropdusterTestCaseMediaMixin


class TestImageFile(CropdusterTestCaseMediaMixin, test.TestCase):

    def test_protocol_relative_path_is_invalid(self):
        # urlopen() raises ValueError("unknown url type") for
        # protocol-relative URLs, and safe_join() rejects them as storage
        # paths; ImageFile treats them as no image at all
        image_file = ImageFile('//example.com/photo.jpg')
        self.assertIsNone(image_file.name)
        self.assertFalse(image_file)

    @mock.patch.object(ImageFile, 'download_image_url')
    def test_protocol_relative_path_is_not_downloaded(self, download_image_url):
        ImageFile('//example.com/photo.jpg')
        download_image_url.assert_not_called()

    @mock.patch.object(ImageFile, 'download_image_url')
    def test_absolute_http_urls_are_downloaded(self, download_image_url):
        img_path = self.create_unique_image('img.jpg')
        download_image_url.return_value = img_path
        for url in ('http://example.com/photo.jpg', 'https://example.com/photo.jpg'):
            image_file = ImageFile(url)
            download_image_url.assert_called_with(url)
            self.assertEqual(image_file.name, img_path)
