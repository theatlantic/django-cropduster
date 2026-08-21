import os
from unittest import mock
from urllib.error import URLError
from urllib.parse import urlsplit

import PIL.Image
import pytest

from django import test
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile

from cropduster.exceptions import (
    CropDusterConfigurationError, CropDusterFileMissing, CropDusterResizeException,
    ImageTooSmallError)
from cropduster.models import Image, Thumb
from cropduster.resizing import Box, Size
from cropduster.services.attach import attach, copy_image
from cropduster.services.payload import build_payload

from .helpers import CropdusterTestCaseMediaMixin, FILESYSTEM_STORAGES
from .models import Article, OptionalSizes


def url_without_query(url):
    """Return a storage URL without its query string or fragment."""
    return urlsplit(url)._replace(query='', fragment='').geturl()


class AttachTestCase(CropdusterTestCaseMediaMixin, test.TestCase):
    """Create a stored source image for attachment tests."""

    def setUp(self):
        super(AttachTestCase, self).setUp()
        self.source = self.create_unique_image('img.jpg')

    def storage(self):
        return Image._meta.get_field('image').storage

    def image_for(self, instance, field_identifier=''):
        return Image.objects.get(
            content_type=ContentType.objects.get_for_model(type(instance)),
            object_id=instance.pk, field_identifier=field_identifier)

    def assertStored(self, image, size_name, tmp=False):
        path = image.get_image_path(size_name, tmp=tmp)
        self.assertTrue(self.storage().exists(path), "%s is not in storage" % path)

    def assertNotStored(self, image, size_name, tmp=False):
        path = image.get_image_path(size_name, tmp=tmp)
        self.assertFalse(self.storage().exists(path), "%s is in storage" % path)

    def stored_files(self, path=''):
        """Return every stored file name below ``path``."""
        directories, files = self.storage().listdir(path)
        names = {
            os.path.join(path, name) if path else name
            for name in files}
        for directory in directories:
            child = os.path.join(path, directory) if path else directory
            names.update(self.stored_files(child))
        return names


class TestAttachToASavedInstance(AttachTestCase):

    def setUp(self):
        super(TestAttachToASavedInstance, self).setUp()
        self.article = Article.objects.create(title='Attached')

    def test_the_image_is_attached_and_every_size_is_cropped(self):
        result = attach(self.article, 'lead_image', self.source)

        self.assertEqual(sorted(result.thumbs), ['main', 'no_height', 'thumb'])
        self.assertEqual(result.errors, {})
        self.assertEqual(result.image, self.image_for(self.article))
        self.assertEqual((result.image.width, result.image.height), (674, 800))
        for size_name in ('original', '_preview', 'main', 'thumb', 'no_height'):
            self.assertStored(result.image, size_name)

    def test_the_original_is_copied_into_a_directory_of_its_own(self):
        result = attach(self.article, 'lead_image', self.source)

        self.assertNotEqual(result.image.name, self.source)
        self.assertTrue(result.image.name.startswith('article/lead_image/'))
        self.assertEqual(os.path.basename(result.image.name), 'original.jpg')

    def test_the_field_holds_the_image_it_was_given(self):
        result = attach(self.article, 'lead_image', self.source)

        self.assertEqual(self.article.lead_image.name, result.image.name)
        self.assertEqual(self.article.lead_image.related_object, result.image)
        self.assertEqual(
            Article.objects.get(pk=self.article.pk).lead_image.name, result.image.name)

    def test_the_crops_belong_to_the_image(self):
        result = attach(self.article, 'lead_image', self.source)

        self.assertEqual(
            {t.name for t in result.image.thumbs.all()},
            {'main', 'thumb', 'no_height'})
        self.assertEqual(
            result.thumbs['thumb'].reference_thumb_id, result.thumbs['main'].pk)

    def test_the_crops_are_not_temporary(self):
        """Use permanent filenames when the target object is already saved."""
        result = attach(self.article, 'lead_image', self.source)

        self.assertFalse(result.tmp)
        self.assertNotStored(result.image, 'main', tmp=True)

    def test_metadata_lands_on_the_image(self):
        result = attach(self.article, 'lead_image', self.source, metadata={
            'attribution': 'A Photographer',
            'attribution_link': 'https://example.com/',
            'caption': 'A caption',
            'alt_text': 'A description'})

        image = self.image_for(self.article)
        self.assertEqual(image.attribution, 'A Photographer')
        self.assertEqual(image.attribution_link, 'https://example.com/')
        self.assertEqual(image.caption, 'A caption')
        self.assertEqual(image.alt_text, 'A description')
        self.assertEqual(result.payload()['metadata']['caption'], 'A caption')

    def test_metadata_is_only_metadata(self):
        with mock.patch('cropduster.services.attach._store_original') as store:
            with self.assertRaises(TypeError):
                attach(
                    self.article, 'lead_image', self.source,
                    metadata={'width': 12})

        store.assert_not_called()

    def test_sizes_may_be_given_instead_of_the_fields(self):
        result = attach(
            self.article, 'lead_image', self.source, sizes=[Size('square', w=400, h=400)])

        self.assertEqual(sorted(result.thumbs), ['square'])
        self.assertStored(result.image, 'square')

    def test_upload_to_may_be_given_instead_of_the_fields(self):
        result = attach(
            self.article, 'lead_image', self.source, upload_to='elsewhere')

        self.assertTrue(result.image.name.startswith('elsewhere/'))

    def test_the_preview_may_be_skipped(self):
        result = attach(self.article, 'lead_image', self.source, preview=False)

        self.assertIsNone(result.preview)
        self.assertNotStored(result.image, '_preview')

    def test_a_second_attach_orphans_the_image_it_replaces(self):
        first = attach(self.article, 'lead_image', self.source).image

        second = attach(self.article, 'lead_image', self.source).image

        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(self.image_for(self.article), second)
        first.refresh_from_db()
        self.assertIsNone(first.object_id)


class TestAttachToAnUnsavedInstance(AttachTestCase):

    def test_the_crops_are_orphans_rendered_under_temporary_names(self):
        article = Article(title='Not yet')

        result = attach(article, 'lead_image', self.source, commit=False)

        self.assertTrue(result.tmp)
        self.assertIsNone(result.image.pk)
        self.assertEqual(sorted(result.thumbs), ['main', 'no_height', 'thumb'])
        for thumb in result.thumbs.values():
            self.assertIsNotNone(thumb.pk, "an orphan crop still needs a pk")
            self.assertIsNone(thumb.image_id)
        self.assertStored(result.image, 'main', tmp=True)
        self.assertNotStored(result.image, 'main', tmp=False)

    def test_the_field_holds_the_image_the_instance_has_not_saved_yet(self):
        article = Article(title='Not yet')

        result = attach(article, 'lead_image', self.source, commit=False)

        self.assertEqual(article.lead_image.name, result.image.name)
        self.assertEqual(article.lead_image.related_object, result.image)

    def test_committing_saves_the_instance_and_attaches_everything_to_it(self):
        article = Article(title='Save me')

        result = attach(article, 'lead_image', self.source, commit=True)

        self.assertIsNotNone(article.pk)
        self.assertEqual(self.image_for(article), result.image)
        self.assertEqual(
            {t.name for t in result.image.thumbs.all()},
            {'main', 'thumb', 'no_height'})
        # Attaching each Thumb promotes its temporary rendition.
        self.assertStored(result.image, 'main')
        self.assertNotStored(result.image, 'main', tmp=True)

    def test_committing_non_temporary_crops_attaches_the_orphan_rows(self):
        article = Article(title='Save without temporary names')

        result = attach(
            article, 'lead_image', self.source, commit=True, tmp=False)

        self.assertFalse(result.tmp)
        self.assertEqual(
            {thumb.image_id for thumb in result.thumbs.values()},
            {result.image.pk})
        self.assertStored(result.image, 'main')

    def test_orphaned_crops_are_adopted_when_the_form_is_saved(self):
        """Attach orphan crops after the form saves its object."""
        article = Article(title='Pinned')
        result = attach(article, 'lead_image', self.source, commit=False, tmp=True)

        result.orphan_thumbs()
        self.assertEqual(
            list(Thumb.objects.filter(image__isnull=True).values_list('name', flat=True)),
            ['main', 'thumb', 'no_height'])

        # Reproduce the formset save using the Thumb primary keys posted by the
        # widget.
        article.save()
        image = result.image
        image.content_object = article
        image.save()
        image.thumbs.set(Thumb.objects.filter(pk__in=[t.pk for t in result.thumbs.values()]))

        self.assertEqual(
            {t.name for t in image.thumbs.all()}, {'main', 'thumb', 'no_height'})
        self.assertStored(image, 'main')
        self.assertNotStored(image, 'main', tmp=True)


class TestAttachUnderTemporaryNames(AttachTestCase):
    """Create temporary crops for a saved instance.

    This matches the dialog flow: a view can return the temporary crops to a
    widget, and the formset attaches them when the object is saved.
    """

    def setUp(self):
        super(TestAttachUnderTemporaryNames, self).setUp()
        self.article = Article.objects.create(title='Mid-form')

    def assertPayloadResolves(self, result):
        """Assert that each payload URL has a corresponding stored file."""
        payload = result.payload()
        self.assertEqual(sorted(payload['thumbs']), ['main', 'no_height', 'thumb'])
        for name, entry in payload['thumbs'].items():
            self.assertEqual(entry['tmp'], result.tmp, name)
            self.assertEqual(
                url_without_query(entry['url']),
                url_without_query(
                    result.image.get_image_url(name, tmp=result.tmp)),
                name)
            self.assertStored(result.image, name, tmp=result.tmp)
        return payload

    def test_the_payload_addresses_the_files_that_were_written(self):
        result = attach(
            self.article, 'lead_image', self.source, tmp=True, commit=False)

        self.assertTrue(result.tmp)
        payload = self.assertPayloadResolves(result)
        self.assertTrue(
            payload['thumbs']['main']['url'].split('?')[0].endswith('main_tmp.jpg'),
            payload['thumbs']['main']['url'])

    def test_the_crops_wait_unattached_for_a_form_to_adopt_them(self):
        result = attach(
            self.article, 'lead_image', self.source, tmp=True, commit=False)

        for name, thumb in result.thumbs.items():
            self.assertIsNotNone(thumb.pk, "an orphan crop still needs a pk")
            self.assertIsNone(thumb.image_id, name)
            self.assertNotStored(result.image, name, tmp=False)

    def test_adoption_promotes_every_rendition(self):
        result = attach(
            self.article, 'lead_image', self.source, tmp=True, commit=False)
        result.orphan_thumbs()
        image = result.image

        # What the formset does with the crops the widget posts back by pk.
        image.thumbs.set(
            Thumb.objects.filter(pk__in=[t.pk for t in result.thumbs.values()]))

        self.assertEqual(
            {t.name for t in image.thumbs.all()}, {'main', 'thumb', 'no_height'})
        for name in ('main', 'thumb', 'no_height'):
            self.assertStored(image, name)
            self.assertNotStored(image, name, tmp=True)

    def test_committing_adopts_them_there_and_then(self):
        result = attach(self.article, 'lead_image', self.source, tmp=True)

        self.assertFalse(result.tmp)
        self.assertPayloadResolves(result)
        self.assertEqual(
            {t.name for t in result.image.thumbs.all()},
            {'main', 'thumb', 'no_height'})


class TestAttachSources(AttachTestCase):

    def setUp(self):
        super(TestAttachSources, self).setUp()
        self.article = Article.objects.create(title='Sourced')

    def test_a_file(self):
        with self.storage().open(self.source, 'rb') as f:
            uploaded = SimpleUploadedFile('uploaded.jpg', f.read())

        result = attach(self.article, 'lead_image', uploaded)

        self.assertEqual((result.image.width, result.image.height), (674, 800))
        self.assertIn('/uploaded/original.jpg', result.image.name)

    def test_an_absolute_local_path(self):
        path = os.path.join(os.path.dirname(__file__), 'data', 'img.jpg')

        result = attach(self.article, 'lead_image', path)

        self.assertEqual((result.image.width, result.image.height), (674, 800))
        self.assertStored(result.image, 'main')

    def test_a_pil_image(self):
        result = attach(
            self.article, 'lead_image', PIL.Image.new('RGB', (800, 600), 'red'))

        self.assertEqual((result.image.width, result.image.height), (800, 600))
        self.assertEqual(os.path.basename(result.image.name), 'original.png')
        self.assertStored(result.image, 'main')

    def test_a_url_is_downloaded_and_adopted_where_it_lands(self):
        downloaded = mock.Mock(name=None)
        downloaded.name = self.source

        with mock.patch('cropduster.services.attach.ImageFile') as image_file:
            image_file.return_value = downloaded
            result = attach(
                self.article, 'lead_image', 'https://example.com/photo.jpg')

        image_file.assert_called_once_with(
            'https://example.com/photo.jpg', upload_to='article/lead_image/%Y/%m')
        self.assertEqual(result.image.name, self.source)
        self.assertStored(result.image, 'main')

    def test_a_download_that_produced_nothing_is_an_error(self):
        nothing = mock.Mock()
        nothing.name = None

        with mock.patch('cropduster.services.attach.ImageFile') as image_file:
            image_file.return_value = nothing
            with self.assertRaises(CropDusterFileMissing):
                attach(self.article, 'lead_image', 'https://example.com/photo.jpg')

    def test_a_path_that_is_not_there_is_an_error(self):
        with self.assertRaises(CropDusterFileMissing):
            attach(self.article, 'lead_image', 'nowhere/original.jpg')

    def test_a_field_that_is_not_a_cropduster_field_is_an_error(self):
        with self.assertRaises(CropDusterConfigurationError):
            attach(self.article, 'title', self.source)


class TestAttachCrops(AttachTestCase):

    def setUp(self):
        super(TestAttachCrops, self).setUp()
        self.article = Article.objects.create(title='Cropped')

    def test_a_box_hint_frames_the_size_it_names(self):
        result = attach(
            self.article, 'lead_image', self.source,
            crops={'main': Box(0, 0, 674, 400)})

        main = result.thumbs['main']
        self.assertEqual(
            (main.crop_x, main.crop_y, main.crop_w, main.crop_h), (37, 0, 600, 480))
        # The size that was not named is framed by the whole image as usual.
        self.assertEqual(
            (result.thumbs['no_height'].crop_w, result.thumbs['no_height'].crop_h),
            (674, 800))

    def test_a_tuple_hint_is_read_as_x_y_w_h(self):
        result = attach(
            self.article, 'lead_image', self.source, crops={'main': (0, 0, 674, 400)})

        main = result.thumbs['main']
        self.assertEqual(
            (main.crop_x, main.crop_y, main.crop_w, main.crop_h), (37, 0, 600, 480))

    def test_a_thumb_hint_frames_the_size_it_names(self):
        drawn = Thumb(name='drawn', crop_x=0, crop_y=0, crop_w=674, crop_h=400)

        result = attach(
            self.article, 'lead_image', self.source, crops={'main': drawn})

        main = result.thumbs['main']
        self.assertEqual(
            (main.crop_x, main.crop_y, main.crop_w, main.crop_h), (37, 0, 600, 480))

    def test_an_auto_size_follows_the_crop_of_the_size_it_belongs_to(self):
        result = attach(
            self.article, 'lead_image', self.source,
            crops={'main': Box(0, 0, 674, 400)})

        auto = result.thumbs['thumb']
        self.assertEqual(auto.reference_thumb_id, result.thumbs['main'].pk)
        self.assertIsNone(auto.crop_x)
        self.assertEqual((auto.width, auto.height), (110, 90))

    def test_a_box_drawn_for_a_size_that_is_not_being_cropped_is_an_error(self):
        """Reject a crop name that does not match a requested size."""
        with self.assertRaises(ValueError) as caught:
            attach(self.article, 'lead_image', self.source,
                   crops={'maim': (0, 0, 674, 400), 'thumb': (0, 0, 674, 400)})

        message = str(caught.exception)
        self.assertIn("'maim'", message)
        self.assertIn("'thumb'", message, "an auto size has no box of its own")
        self.assertIn("'main'", message)

    def test_nothing_is_stored_for_a_call_that_is_refused(self):
        with self.assertRaises(ValueError):
            attach(self.article, 'lead_image', self.source, crops={'maim': (0, 0, 1, 1)})

        self.assertFalse(Image.objects.exists())


class TestAttachFailures(AttachTestCase):

    def setUp(self):
        super(TestAttachFailures, self).setUp()
        self.optional = OptionalSizes.objects.create(slug='optional')

    def test_an_image_too_small_for_a_required_size_is_refused(self):
        with self.assertRaises(ImageTooSmallError) as caught:
            attach(self.optional, 'image', self.source,
                   sizes=[Size('huge', w=2000, h=1000)])

        self.assertEqual(caught.exception.min_size, (2000, 1000))
        self.assertEqual(caught.exception.actual_size, (674, 800))

    def test_a_size_that_is_not_required_is_collected_rather_than_raised(self):
        """`optional` is 1200x960; the image is 674x800."""
        result = attach(self.optional, 'image', self.source)

        self.assertEqual(sorted(result.thumbs), ['main'])
        self.assertEqual(sorted(result.errors), ['optional'])
        self.assertIsInstance(result.errors['optional'], CropDusterResizeException)

    def test_a_size_that_is_not_required_is_collected_even_when_strict(self):
        result = attach(self.optional, 'image', self.source, permissive=False)

        self.assertEqual(sorted(result.errors), ['optional'])

    def test_a_required_size_that_cannot_be_cropped_is_collected_when_permissive(self):
        """A hint reaching outside the image leaves too little to crop."""
        result = attach(
            self.optional, 'image', self.source, crops={'main': (0, 0, 2000, 2000)})

        self.assertEqual(sorted(result.errors), ['main'])
        self.assertEqual(result.thumbs, {})

    def test_a_required_size_that_cannot_be_cropped_is_raised_when_strict(self):
        with self.assertRaises(CropDusterResizeException):
            attach(self.optional, 'image', self.source, permissive=False,
                   crops={'main': (0, 0, 2000, 2000)})

    def test_a_strict_failure_does_not_replace_the_attached_image(self):
        previous = attach(
            self.optional, 'image', self.source,
            sizes=[Size('kept', w=100, h=100)]).image
        files_before = self.stored_files()
        image_count = Image.objects.count()
        thumb_count = Thumb.objects.count()

        with self.assertRaises(CropDusterResizeException):
            attach(
                self.optional, 'image', self.source,
                sizes=[
                    Size('first', w=100, h=100),
                    Size('second', w=600, h=480),
                ],
                crops={'second': (0, 0, 2000, 2000)},
                permissive=False, commit=False)

        previous.refresh_from_db()
        self.optional.refresh_from_db()
        self.assertEqual(previous.object_id, self.optional.pk)
        self.assertEqual(self.optional.image.related_object, previous)
        self.assertEqual(Image.objects.count(), image_count)
        self.assertEqual(Thumb.objects.count(), thumb_count)
        self.assertEqual(self.stored_files(), files_before)

    def test_attach_does_not_accept_a_per_call_storage(self):
        with self.assertRaises(TypeError):
            attach(
                self.optional, 'image', self.source,
                storage=self.storage())


class TestAttachFieldIdentifier(AttachTestCase):

    def setUp(self):
        super(TestAttachFieldIdentifier, self).setUp()
        self.article = Article.objects.create(title='Two fields')

    def test_each_field_gets_its_own_image(self):
        lead = attach(self.article, 'lead_image', self.source)
        alt = attach(self.article, 'alt_image', self.source)

        self.assertEqual(lead.image.field_identifier, '')
        self.assertEqual(alt.image.field_identifier, 'alt')
        self.assertEqual(self.image_for(self.article), lead.image)
        self.assertEqual(self.image_for(self.article, 'alt'), alt.image)

    def test_each_field_gets_its_own_sizes(self):
        lead = attach(self.article, 'lead_image', self.source)
        alt = attach(self.article, 'alt_image', self.source)

        self.assertEqual(sorted(lead.thumbs), ['main', 'no_height', 'thumb'])
        self.assertEqual(sorted(alt.thumbs), ['wide'])

    def test_the_columns_of_both_fields_are_kept_up_to_date(self):
        lead = attach(self.article, 'lead_image', self.source)
        alt = attach(self.article, 'alt_image', self.source)

        article = Article.objects.get(pk=self.article.pk)
        self.assertEqual(article.lead_image.name, lead.image.name)
        self.assertEqual(article.alt_image.name, alt.image.name)


class TestAttachSourcesSeam(AttachTestCase):

    def setUp(self):
        super(TestAttachSourcesSeam, self).setUp()
        self.article = Article.objects.create(title='One source')

    def test_naming_another_source_for_a_crop_is_not_implemented(self):
        with self.assertRaises(NotImplementedError):
            attach(self.article, 'lead_image', self.source,
                   sources={'main': 'somewhere/else/original.jpg'})

    def test_naming_the_image_being_attached_is_the_same_as_naming_nothing(self):
        result = attach(
            self.article, 'lead_image', self.source,
            sources={'main': self.source, 'no_height': self.source})

        self.assertEqual(sorted(result.thumbs), ['main', 'no_height', 'thumb'])


@test.override_settings(STORAGES=FILESYSTEM_STORAGES)
class TestAttachPayload(AttachTestCase):

    def setUp(self):
        super(TestAttachPayload, self).setUp()
        self.article = Article.objects.create(title='Payload')

    def test_the_payload_describes_the_state_the_api_would_report(self):
        result = attach(self.article, 'lead_image', self.source)

        saved = Image.objects.get(pk=result.image.pk)
        self.assertEqual(
            result.payload(),
            build_payload(saved, sizes=result.sizes, preview=result.preview))

    def downstream_crop_data(self, image, thumbs):
        """
        A downstream CMS's crop-data helper, transcribed.

        Pages that fill a cropduster widget in from the server respond with
        this dict as ``data.image``, and ``payload(legacy=True)`` replaces
        that helper; its shape is therefore the specification for the legacy
        payload rather than the other way round.
        """
        thumb_data = {}
        preview_url, preview_w, preview_h = '', None, None
        for thumb in thumbs:
            crop_data = {
                'id': thumb.pk,
                'name': thumb.name,
                'width': thumb.width,
                'height': thumb.height,
                'url': thumb.get_url(),
            }
            thumb_data[thumb.name] = crop_data
            if not preview_url:
                preview_url = crop_data['url']
                preview_w = crop_data['width']
                preview_h = crop_data['height']

        return {
            'thumbs': thumb_data,
            'preview_url': preview_url,
            'preview_w': preview_w,
            'preview_h': preview_h,
            'alt_text': getattr(image, 'alt_text', None) or '',
            'attribution': getattr(image, 'attribution', None) or '',
            'crop': {
                'image_id': '',
                'orig_image': image.name,
                'thumbs': thumb_data,
            },
        }

    def test_the_legacy_payload_is_what_the_widget_completes_with(self):
        """`CropDuster.complete()` reads crop.image_id, crop.orig_image,
        crop.thumbs, preview_* and the presence of a top-level thumbs; the
        pages around it read the metadata from the same dict."""
        result = attach(self.article, 'lead_image', self.source, metadata={
            'attribution': 'A Photographer', 'alt_text': 'A description'})
        image = result.image
        expected = self.downstream_crop_data(image, result.thumbs.values())

        payload = result.payload(legacy=True)

        self.assertEqual(payload, {
            'crop': {
                'image_id': image.pk,
                'orig_image': image.name,
                'orig_w': 674,
                'orig_h': 800,
                'thumbs': expected['crop']['thumbs'],
            },
            'thumbs': [],
            'initial': True,
            'preview_url': expected['preview_url'],
            'preview_w': expected['preview_w'],
            'preview_h': expected['preview_h'],
            'attribution': 'A Photographer',
            'attribution_link': None,
            'caption': None,
            'alt_text': 'A description',
        })

    def test_the_legacy_payload_answers_what_the_helper_it_replaces_did(self):
        result = attach(self.article, 'lead_image', self.source, metadata={
            'attribution': 'A Photographer', 'alt_text': 'A description'})
        expected = self.downstream_crop_data(result.image, result.thumbs.values())

        payload = result.payload(legacy=True)

        for key in ('preview_url', 'preview_w', 'preview_h', 'attribution', 'alt_text'):
            self.assertEqual(payload[key], expected[key], key)
        self.assertEqual(payload['crop']['orig_image'], expected['crop']['orig_image'])
        self.assertEqual(payload['crop']['thumbs'], expected['crop']['thumbs'])

        # The two deltas, neither of which any client reads: the top-level
        # thumbs is only checked for being an object, and the helper hardcoded
        # an empty image_id because it only ever described an unsaved image.
        self.assertEqual(payload['thumbs'], [])
        self.assertEqual(payload['crop']['image_id'], result.image.pk)

    def test_the_legacy_preview_is_the_first_crop(self):
        """Not the preview rendition: the widget draws it as the image."""
        result = attach(self.article, 'lead_image', self.source)

        payload = result.payload(legacy=True)

        main = result.thumbs['main']
        self.assertEqual(payload['preview_url'], main.get_url())
        self.assertEqual(
            (payload['preview_w'], payload['preview_h']), (main.width, main.height))
        self.assertNotEqual(
            payload['preview_url'], result.image.get_image_url('preview'))

    def test_the_legacy_payload_of_an_image_with_no_crops_reports_no_preview(self):
        result = attach(
            self.article, 'lead_image', self.source,
            sizes=[Size('huge', w=4000, h=4000, required=False)])

        payload = result.payload(legacy=True)

        self.assertEqual(payload['crop']['thumbs'], {})
        self.assertEqual(payload['preview_url'], '')
        self.assertIsNone(payload['preview_w'])
        self.assertIsNone(payload['preview_h'])

    def test_the_legacy_payload_of_an_unsaved_image_reports_no_id(self):
        article = Article(title='Unsaved')
        result = attach(article, 'lead_image', self.source, commit=False)

        payload = result.payload(legacy=True)

        self.assertEqual(payload['crop']['image_id'], '')
        self.assertEqual(sorted(payload['crop']['thumbs']), ['main', 'no_height', 'thumb'])
        self.assertTrue(
            payload['crop']['thumbs']['main']['url'].split('?')[0].endswith('main_tmp.jpg'))

    def test_crop_names_may_be_sanitized_for_templates(self):
        result = attach(
            self.article, 'lead_image', self.source,
            sizes=[Size('main', w=300, h=240, auto=[Size('main@2x', w=600, h=480)])])

        payload = result.payload(legacy=True, sanitize=True)

        self.assertEqual(sorted(payload['crop']['thumbs']), ['main', 'main_2x'])


class TestAttachWithoutRenditions(AttachTestCase):
    """Metadata-only: the crops are geometry, rendered elsewhere on demand."""

    def setUp(self):
        super(TestAttachWithoutRenditions, self).setUp()
        self.article = Article.objects.create(title='Metadata only')

    @test.override_settings(CROPDUSTER_CREATE_THUMBS=False)
    def test_the_crops_are_rows_without_files(self):
        result = attach(self.article, 'lead_image', self.source)

        self.assertEqual(sorted(result.thumbs), ['main', 'no_height', 'thumb'])
        main = result.thumbs['main']
        self.assertEqual(
            (main.crop_x, main.crop_y, main.crop_w, main.crop_h), (0, 130, 674, 539))
        self.assertStored(result.image, 'original')
        self.assertNotStored(result.image, 'main')

    @test.override_settings(CROPDUSTER_CREATE_THUMBS=False)
    def test_a_copy_writes_nothing_at_all(self):
        """The original and its preview are already there to be shared."""
        attached = attach(self.article, 'lead_image', self.source)
        other = Article.objects.create(title='Copied to')

        result = copy_image(attached.image, other, 'alt_image')

        self.assertEqual(sorted(result.thumbs), ['wide'])
        self.assertEqual(result.image.name, attached.image.name)
        self.assertNotStored(result.image, 'wide')


class TestCopyImage(AttachTestCase):

    def setUp(self):
        super(TestCopyImage, self).setUp()
        self.article = Article.objects.create(title='Copied from')
        self.attached = attach(
            self.article, 'lead_image', self.source,
            metadata={'attribution': 'A Photographer', 'caption': 'A caption'})

    def test_the_copy_shares_the_original_and_inherits_its_metadata(self):
        other = Article.objects.create(title='Copied to')

        result = copy_image(self.article.lead_image, other, 'lead_image')

        self.assertEqual(result.image.name, self.attached.image.name)
        self.assertNotEqual(result.image.pk, self.attached.image.pk)
        self.assertEqual(result.image.attribution, 'A Photographer')
        self.assertEqual(result.image.caption, 'A caption')
        self.assertEqual((result.image.width, result.image.height), (674, 800))

    def test_metadata_may_be_overridden(self):
        other = Article.objects.create(title='Copied to')

        result = copy_image(
            self.article.lead_image, other, 'lead_image',
            metadata={'caption': 'Another caption'})

        self.assertEqual(result.image.attribution, 'A Photographer')
        self.assertEqual(result.image.caption, 'Another caption')

    def test_an_image_may_be_copied_as_well_as_a_field_file(self):
        other = Article.objects.create(title='Copied to')

        result = copy_image(self.attached.image, other, 'lead_image')

        self.assertEqual(result.image.name, self.attached.image.name)
        self.assertEqual(sorted(result.thumbs), ['main', 'no_height', 'thumb'])

    def test_the_framing_of_the_source_carries_across(self):
        """The target field's sizes are cropped from the boxes already drawn."""
        drawn = self.attached.thumbs['main']
        drawn.crop_x, drawn.crop_y, drawn.crop_w, drawn.crop_h = 0, 0, 674, 400
        drawn.save()
        other = Article.objects.create(title='Copied to')

        result = copy_image(self.article.lead_image, other, 'alt_image')

        wide = result.thumbs['wide']
        self.assertEqual((wide.crop_x, wide.crop_y, wide.crop_w, wide.crop_h),
                         (0, 32, 674, 337))

    def test_a_crop_may_be_hinted_over_the_source_framing(self):
        other = Article.objects.create(title='Copied to')

        result = copy_image(
            self.article.lead_image, other, 'alt_image',
            crops={'wide': (0, 400, 674, 400)})

        wide = result.thumbs['wide']
        self.assertEqual((wide.crop_x, wide.crop_y, wide.crop_w, wide.crop_h),
                         (0, 432, 674, 337))

    def test_copying_to_an_unsaved_instance_leaves_orphans(self):
        other = Article(title='Not yet')

        result = copy_image(self.article.lead_image, other, 'lead_image', commit=False)

        self.assertTrue(result.tmp)
        self.assertIsNone(result.image.pk)
        for thumb in result.thumbs.values():
            self.assertIsNone(thumb.image_id)

    def test_the_source_must_be_a_cropduster_image(self):
        other = Article.objects.create(title='Copied to')

        with self.assertRaises(CropDusterConfigurationError):
            copy_image(self.source, other, 'lead_image')

    def test_copy_does_not_accept_a_per_call_storage(self):
        with self.assertRaises(TypeError):
            copy_image(
                self.attached.image,
                Article.objects.create(title='Copied to'), 'lead_image',
                storage=self.storage())

    def test_a_required_size_that_cannot_be_cropped_is_raised(self):
        """
        The opposite default to ``attach``: a copy is made on an object's
        behalf, with nowhere to report ``result.errors`` to.
        """
        other = Article.objects.create(title='Copied to')

        with self.assertRaises(CropDusterResizeException):
            copy_image(self.attached.image, other, 'lead_image',
                       crops={'main': (0, 0, 2000, 2000)})

    def test_permissive_collects_it_the_way_attach_does(self):
        other = Article.objects.create(title='Copied to')

        result = copy_image(self.attached.image, other, 'lead_image',
                            permissive=True, crops={'main': (0, 0, 2000, 2000)})

        self.assertEqual(sorted(result.errors), ['main'])

    def test_an_image_too_small_for_the_target_field_is_refused(self):
        small = OptionalSizes.objects.create(slug='small')
        attach(small, 'image', PIL.Image.new('RGB', (500, 400), 'blue'),
               sizes=[Size('tiny', w=100, h=100)])

        with self.assertRaises(ImageTooSmallError) as caught:
            copy_image(
                small.image, Article.objects.create(title='Copied to'), 'lead_image')

        self.assertEqual(caught.exception.actual_size, (500, 400))

    def test_an_original_that_is_gone_cannot_be_copied(self):
        self.storage().delete(self.attached.image.name)
        other = Article.objects.create(title='Copied to')

        with self.assertRaises(CropDusterFileMissing):
            copy_image(self.attached.image, other, 'lead_image')

    def test_an_original_that_cannot_be_fetched_is_missing(self):
        self.storage().delete(self.attached.image.name)
        other = Article.objects.create(title='Copied to')

        with mock.patch.object(
                Image, 'url', 'https://cdn.example.com/gone/original.jpg'):
            with mock.patch(
                    'cropduster.services.attach.ImageFile',
                    side_effect=URLError('not found')):
                with self.assertRaises(CropDusterFileMissing):
                    copy_image(self.attached.image, other, 'lead_image')

    def test_an_original_that_is_gone_is_fetched_back_from_its_url(self):
        """It can have been moved to a CDN, or restored without its media."""
        self.storage().delete(self.attached.image.name)
        other = Article.objects.create(title='Copied to')
        recovered = mock.Mock()
        recovered.name = self.source

        with mock.patch.object(
                Image, 'url', 'https://cdn.example.com/gone/original.jpg'):
            with mock.patch('cropduster.services.attach.ImageFile') as image_file:
                image_file.return_value = recovered
                result = copy_image(self.attached.image, other, 'lead_image')

        self.assertEqual(result.image.name, self.source)

    @test.override_settings(CROPDUSTER_REMOTE_IMAGE_FETCH=False)
    def test_it_is_not_fetched_back_when_downloading_is_turned_off(self):
        self.storage().delete(self.attached.image.name)
        other = Article.objects.create(title='Copied to')

        with mock.patch.object(
                Image, 'url', 'https://cdn.example.com/gone/original.jpg'):
            with self.assertRaises(CropDusterFileMissing):
                copy_image(self.attached.image, other, 'lead_image')

    def test_reuse_keeps_the_row_the_field_already_has(self):
        result = copy_image(
            self.attached.image, self.article, 'lead_image', reuse=True)

        self.assertEqual(result.image.pk, self.attached.image.pk)
        self.assertEqual(
            {t.pk for t in result.thumbs.values()},
            {t.pk for t in self.attached.thumbs.values()})

    def test_reuse_keeps_a_box_the_source_has_nothing_to_say_about(self):
        """A source with no crops contributes no framing, so the box is kept."""
        drawn = self.attached.thumbs['main']
        drawn.crop_x, drawn.crop_y, drawn.crop_w, drawn.crop_h = 20, 30, 600, 480
        drawn.save()
        bare = Image.objects.create(
            image=self.attached.image.name, width=674, height=800,
            content_type=ContentType.objects.get_for_model(Article),
            object_id=Article.objects.create(title='No crops').pk)

        result = copy_image(bare, self.article, 'lead_image', reuse=True)

        main = result.thumbs['main']
        self.assertEqual(main.pk, drawn.pk)
        self.assertEqual(
            (main.crop_x, main.crop_y, main.crop_w, main.crop_h), (20, 30, 600, 480))

    def test_skip_existing_keeps_the_renditions_that_are_already_there(self):
        image = self.attached.image
        with self.storage().open(image.get_image_path('main'), 'wb') as f:
            f.write(b'not really a jpeg')

        copy_image(image, self.article, 'lead_image', reuse=True, skip_existing=True)

        with self.storage().open(image.get_image_path('main'), 'rb') as f:
            self.assertEqual(f.read(), b'not really a jpeg')

    def test_skip_existing_makes_the_temporary_file_it_reports(self):
        image = self.attached.image

        result = copy_image(
            image, self.article, 'lead_image', reuse=True,
            skip_existing=True, tmp=True, commit=False)

        self.assertTrue(result.tmp)
        self.assertStored(image, 'main', tmp=True)
        self.assertIn('_tmp.', result.payload()['thumbs']['main']['file_url'])

    def test_without_skip_existing_the_renditions_are_made_again(self):
        image = self.attached.image
        with self.storage().open(image.get_image_path('main'), 'wb') as f:
            f.write(b'not really a jpeg')

        copy_image(image, self.article, 'lead_image', reuse=True)

        with self.storage().open(image.get_image_path('main'), 'rb') as f:
            self.assertNotEqual(f.read(), b'not really a jpeg')


@pytest.mark.django_db
def test_the_programmatic_api_is_reachable_from_the_package():
    import cropduster

    assert cropduster.attach is attach
    assert cropduster.copy_image is copy_image


def test_both_documented_ways_of_importing_attach_give_the_function():
    """
    ``attach`` names a submodule as well as the function it exports. The two
    paths checked here are the documented ones; ``cropduster.services`` does
    not export the name because the import system binds the submodule there
    as soon as anything imports it.
    """
    from cropduster import attach as from_package
    from cropduster.services.attach import attach as from_module

    assert callable(from_package)
    assert callable(from_module)
    assert from_package is from_module is attach


def test_the_services_package_advertises_only_names_it_can_answer_with():
    import cropduster.services as services

    assert 'attach' not in services.__all__
    for name in services.__all__:
        assert callable(getattr(services, name)), name
