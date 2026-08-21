import os
from io import BytesIO
from urllib.parse import urlsplit

import PIL.Image
import pytest

from django import test
from django.core.files.storage import FileSystemStorage
from django.core.files.uploadedfile import SimpleUploadedFile

from cropduster.exceptions import CropDusterImageException, ImageTooSmallError
from cropduster.models import Image, StandaloneImage
from cropduster.resizing import Size
from cropduster.services.upload import (
    ANIMATED_GIF_WARNING, min_upload_size, preview_dimensions, store_upload)
from cropduster.utils import json

from .helpers import CropdusterTestCaseMediaMixin


SIZES = [
    Size('main', w=600, h=480, auto=[Size('thumb', w=110, h=90)]),
    Size('small', w=100, h=80),
]


def url_without_query(url):
    """Return a storage URL without transient signature parameters."""
    return urlsplit(url)._replace(query='', fragment='').geturl()


def upload_file(name='img.jpg', size=(800, 600), format='JPEG', color='red'):
    buf = BytesIO()
    PIL.Image.new('RGB', size, color).save(buf, format=format)
    return SimpleUploadedFile(name, buf.getvalue())


class TestMinUploadSize(test.SimpleTestCase):

    def test_largest_of_every_size(self):
        self.assertEqual(min_upload_size(SIZES), (600, 480))

    def test_no_sizes_means_no_minimum(self):
        self.assertEqual(min_upload_size([]), (0, 0))
        self.assertEqual(min_upload_size(None), (0, 0))

    def test_for_size_scopes_to_one_size(self):
        self.assertEqual(min_upload_size(SIZES, for_size='small'), (100, 80))

    def test_for_size_reaches_auto_sizes(self):
        self.assertEqual(min_upload_size(SIZES, for_size='thumb'), (110, 90))

    def test_for_size_takes_the_largest_of_a_size_and_its_auto_sizes(self):
        retina = [Size('main', w=600, h=480, auto=[Size('main@2x', w=1200, h=960)])]

        self.assertEqual(min_upload_size(retina, for_size='main'), (1200, 960))

    def test_for_size_must_name_a_size(self):
        with self.assertRaises(ValueError):
            min_upload_size(SIZES, for_size='nope')

    def test_sizes_may_arrive_as_json(self):
        self.assertEqual(min_upload_size(json.dumps(SIZES)), (600, 480))


class TestPreviewDimensions(test.SimpleTestCase):

    def test_scales_down_to_fit(self):
        self.assertEqual(preview_dimensions((1000, 500), (800, 500)), (800, 400))

    def test_leaves_a_smaller_image_alone(self):
        self.assertEqual(preview_dimensions((100, 50), (800, 500)), (100, 50))


class TestStoreUpload(CropdusterTestCaseMediaMixin, test.TestCase):

    def test_stores_the_original_in_its_own_directory(self):
        result = store_upload(upload_file(), upload_to='uploads', sizes=SIZES)

        self.assertEqual(result.original_name, 'uploads/img/original.jpg')
        self.assertTrue(result.image.storage.exists(result.original_name))
        self.assertEqual((result.width, result.height), (800, 600))

    def test_the_image_is_unsaved(self):
        result = store_upload(upload_file(), upload_to='uploads')

        self.assertIsInstance(result.image, Image)
        self.assertIsNone(result.image.pk)
        self.assertIsNone(result.standalone_image)
        self.assertIsNone(result.standalone_thumb)

    def test_md5_is_of_the_stored_file(self):
        import hashlib

        upload = upload_file()
        result = store_upload(upload, upload_to='uploads')

        with result.image.storage.open(result.original_name) as f:
            self.assertEqual(result.md5, hashlib.md5(f.read()).hexdigest())

    def test_writes_a_preview(self):
        result = store_upload(
            upload_file(size=(1000, 500)), upload_to='uploads',
            preview_size=(800, 500))

        self.assertEqual((result.preview.width, result.preview.height), (800, 400))
        self.assertTrue(
            result.image.storage.exists(result.image.get_image_path('_preview')))

    def test_an_image_smaller_than_the_preview_is_not_scaled_up(self):
        result = store_upload(
            upload_file(size=(200, 100)), upload_to='uploads', preview_size=(800, 500))

        self.assertEqual((result.preview.width, result.preview.height), (200, 100))

    def test_too_small_for_the_sizes(self):
        with self.assertRaises(ImageTooSmallError) as caught:
            store_upload(upload_file(size=(100, 100)), upload_to='uploads', sizes=SIZES)

        self.assertEqual(caught.exception.min_size, (600, 480))
        self.assertEqual(caught.exception.actual_size, (100, 100))

    def test_for_size_narrows_what_the_upload_has_to_satisfy(self):
        """Accept a source that satisfies one size but not the complete set."""
        result = store_upload(
            upload_file(size=(120, 100)), upload_to='uploads', sizes=SIZES,
            for_size='small')

        self.assertEqual((result.width, result.height), (120, 100))

    def test_for_size_covers_the_auto_sizes_that_follow_it(self):
        """Include a size's automatic children in its minimum dimensions."""
        result = store_upload(
            upload_file(size=(600, 480)), upload_to='uploads', sizes=SIZES,
            for_size='main')

        self.assertEqual((result.width, result.height), (600, 480))

        with self.assertRaises(ImageTooSmallError) as caught:
            store_upload(
                upload_file(size=(599, 480)), upload_to='uploads', sizes=SIZES,
                for_size='main')

        self.assertEqual(caught.exception.min_size, (600, 480))

    def test_for_size_still_enforces_that_size(self):
        with self.assertRaises(ImageTooSmallError) as caught:
            store_upload(
                upload_file(size=(90, 100)), upload_to='uploads', sizes=SIZES,
                for_size='small')

        self.assertEqual(caught.exception.min_size, (100, 80))

    def test_nothing_is_stored_when_the_upload_is_refused(self):
        with self.assertRaises(ImageTooSmallError):
            store_upload(upload_file(size=(10, 10)), upload_to='uploads', sizes=SIZES)

        self.assertFalse(Image().storage.exists('uploads/img/original.jpg'))
        self.assertFalse(Image().storage.exists('uploads/img'))

    def test_unusable_file(self):
        with self.assertRaises(CropDusterImageException):
            store_upload(
                SimpleUploadedFile('img.jpg', b'not an image'), upload_to='uploads')

    def test_a_per_call_storage_is_not_accepted(self):
        with self.assertRaises(TypeError):
            store_upload(
                upload_file(), upload_to='uploads', storage=object())

    def test_animated_gif_warning(self):
        with open(os.path.join(self.TEST_IMG_DIR, 'animated.gif'), 'rb') as f:
            upload = SimpleUploadedFile('animated.gif', f.read())

        with test.override_settings(CROPDUSTER_GIFSICLE_PATH=''):
            # Preview rendering emits the UserWarning. The structured result
            # separately provides the warning shown to the editor.
            with pytest.warns(UserWarning, match='animated gif support'):
                result = store_upload(upload, upload_to='uploads')

        self.assertEqual(result.warnings, [ANIMATED_GIF_WARNING])

    def test_no_warnings_for_an_ordinary_upload(self):
        self.assertEqual(store_upload(upload_file(), upload_to='uploads').warnings, [])

    def test_sizes_may_arrive_as_json(self):
        """Accept the serialized size list posted by clients."""
        result = store_upload(
            upload_file(), upload_to='uploads', sizes=json.dumps(SIZES))

        self.assertEqual([size.name for size in result.sizes], ['main', 'small'])
        self.assertEqual([type(size) for size in result.sizes], [Size, Size])
        self.assertEqual(result.sizes[0].auto[0].name, 'thumb')

    def test_json_sizes_are_what_the_minimum_is_checked_against(self):
        with self.assertRaises(ImageTooSmallError) as caught:
            store_upload(
                upload_file(size=(100, 100)), upload_to='uploads',
                sizes=json.dumps(SIZES))

        self.assertEqual(caught.exception.min_size, (600, 480))


class TestStoreStandaloneUpload(CropdusterTestCaseMediaMixin, test.TestCase):

    def test_creates_the_standalone_rows_and_the_initial_crop(self):
        result = store_upload(
            upload_file(size=(400, 300)), upload_to='uploads', standalone=True)

        self.assertIsNotNone(result.image.pk)
        self.assertEqual(result.standalone_image.md5, result.md5)
        self.assertEqual(result.image.content_object, result.standalone_image)

        thumb = result.standalone_thumb
        self.assertEqual((thumb.crop_w, thumb.crop_h), (400, 300))
        self.assertEqual((thumb.width, thumb.height), (400, 300))
        # The initial crop is named from its contents and remains unsaved until
        # the client accepts it.
        self.assertEqual(len(thumb.name), 9)

    def test_the_same_bytes_reuse_the_first_image(self):
        first = store_upload(
            upload_file(name='a.jpg'), upload_to='uploads', standalone=True)
        second = store_upload(
            upload_file(name='b.jpg'), upload_to='uploads', standalone=True)

        self.assertEqual(second.image.pk, first.image.pk)
        self.assertEqual(second.original_name, first.original_name)
        self.assertEqual(StandaloneImage.objects.count(), 1)

    def test_a_deduplicated_upload_previews_only_what_it_answers_with(self):
        """Write the preview beside the image retained after deduplication.

        A duplicate upload returns the first ``Image`` row. A preview beside
        the new unreferenced copy would have no URL in the result.
        """
        first = store_upload(
            upload_file(name='a.jpg'), upload_to='uploads', standalone=True)
        second = store_upload(
            upload_file(name='b.jpg'), upload_to='uploads', standalone=True)

        storage = second.image.storage
        self.assertEqual(first.original_name, 'uploads/a/original.jpg')
        self.assertFalse(storage.exists('uploads/b/original.jpg'))

        self.assertFalse(storage.exists('uploads/b/_preview.jpg'))
        self.assertTrue(storage.exists('uploads/a/_preview.jpg'))
        if isinstance(storage, FileSystemStorage):
            self.assertFalse(os.path.isdir(storage.path('uploads/b')))
        self.assertEqual(
            (second.preview.width, second.preview.height),
            (first.preview.width, first.preview.height))

    def test_the_crop_is_attributed_to_the_one_size_that_was_asked_for(self):
        result = store_upload(
            upload_file(), upload_to='uploads', standalone=True,
            sizes=[Size('crop', w=200, h=100)])

        self.assertEqual([size.name for size in result.sizes], ['crop'])
        self.assertEqual(result.sizes[0].w, 200)

    def test_a_json_encoded_size_is_the_one_that_was_asked_for(self):
        result = store_upload(
            upload_file(), upload_to='uploads', standalone=True,
            sizes=json.dumps([Size('crop', w=200, h=100)]))

        self.assertEqual([size.name for size in result.sizes], ['crop'])
        self.assertEqual(result.sizes[0].w, 200)

    def test_ambiguous_sizes_are_answered_with_a_bare_crop(self):
        result = store_upload(
            upload_file(), upload_to='uploads', standalone=True, sizes=SIZES)

        self.assertEqual([size.name for size in result.sizes], ['crop'])
        self.assertIsNone(result.sizes[0].w)
