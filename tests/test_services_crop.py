from io import BytesIO

import PIL.Image

from django import test
from django.contrib.contenttypes.models import ContentType

from cropduster.models import Image, Thumb
from cropduster.resizing import Box, Size
from cropduster.services import crop as crop_service
from cropduster.services.crop import ThumbRequest, apply_crops

from .helpers import CropdusterTestCaseMediaMixin
from .models import Article


MAIN = Size('main', w=600, h=480, auto=[Size('thumb', w=110, h=90)])
NO_HEIGHT = Size('no_height', w=600)


class CropServiceTestCase(CropdusterTestCaseMediaMixin, test.TestCase):
    """Create an image large enough for every crop used by these tests."""

    def setUp(self):
        super(CropServiceTestCase, self).setUp()
        self.image = Image(image=self.create_unique_image('img2.jpg'))

    def saved_image(self):
        """Attach the image to an article and render every configured size."""
        article = Article.objects.create(title='Cropped', lead_image=self.image.name)
        article.lead_image.generate_thumbs()
        return Image.objects.get(
            content_type=ContentType.objects.get_for_model(Article),
            object_id=article.pk, field_identifier='')

    def source(self):
        with self.image.image_file_open() as f:
            pil_image = PIL.Image.open(BytesIO(f.read()))
            pil_image.filename = f.name
        return pil_image


class TestApplyCrops(CropServiceTestCase):

    def test_a_changed_box_renders_the_size_and_its_auto_children(self):
        result = apply_crops(self.image, [ThumbRequest(
            name='main', size=MAIN, crop=Box(0, 0, 1200, 960), changed=True)])

        self.assertEqual(sorted(result.thumbs), ['main', 'thumb'])
        self.assertEqual(result.changed, {'main', 'thumb'})
        self.assertEqual(result.suggestions, {})

        main, auto = result.thumbs['main'], result.thumbs['thumb']
        self.assertEqual((main.width, main.height), (600, 480))
        self.assertEqual((auto.width, auto.height), (110, 90))
        self.assertEqual(auto.reference_thumb_id, main.pk)
        # Renditions remain temporary until the object containing the image is
        # saved.
        self.assertTrue(
            self.image.storage.exists(self.image.get_image_path('main', tmp=True)))
        self.assertFalse(
            self.image.storage.exists(self.image.get_image_path('main', tmp=False)))

    def test_a_changed_box_leaves_the_saved_crop_alone(self):
        """Keep the saved row until the object accepts the replacement crop."""
        image = self.saved_image()
        saved = image.thumbs.get(name='main')

        result = apply_crops(image, [ThumbRequest(
            name='main', size=MAIN, thumb_id=saved.pk, crop=Box(0, 0, 800, 640),
            width=600, height=480, changed=True)])

        self.assertNotEqual(result.thumbs['main'].pk, saved.pk)
        self.assertTrue(Thumb.objects.filter(pk=saved.pk).exists())

    def test_an_unchanged_size_is_copied_to_its_temporary_name(self):
        image = self.saved_image()
        saved = image.thumbs.get(name='no_height')

        result = apply_crops(image, [ThumbRequest(
            name='no_height', size=NO_HEIGHT, thumb_id=saved.pk,
            crop=Box(saved.crop_x, saved.crop_y,
                     saved.crop_x + saved.crop_w, saved.crop_y + saved.crop_h),
            width=saved.width, height=saved.height)])

        self.assertEqual(result.changed, set())
        self.assertTrue(result.outcomes[0].copied)
        self.assertTrue(
            image.storage.exists(image.get_image_path('no_height', tmp=True)))
        self.assertEqual(result.thumbs['no_height'].pk, saved.pk)

    def test_an_unchanged_size_does_not_open_the_original(self):
        image = self.saved_image()
        saved = image.thumbs.get(name='no_height')
        real_open = crop_service.open_stored_image

        def unexpected_open(*args, **kwargs):
            raise AssertionError('the original should not be opened')

        crop_service.open_stored_image = unexpected_open
        self.addCleanup(
            setattr, crop_service, 'open_stored_image', real_open)

        result = apply_crops(image, [ThumbRequest(
            name='no_height', size=NO_HEIGHT, thumb=saved,
            crop=Box(saved.crop_x, saved.crop_y,
                     saved.crop_x + saved.crop_w,
                     saved.crop_y + saved.crop_h),
            width=saved.width, height=saved.height)])

        self.assertTrue(result.outcomes[0].copied)

    def test_a_preloaded_thumb_is_used_instead_of_looking_it_up(self):
        """Reuse the row already loaded while a formset binds its form."""
        image = self.saved_image()
        saved = image.thumbs.get(name='no_height')
        request = dict(
            name='no_height', size=NO_HEIGHT, thumb_id=saved.pk,
            crop=Box(saved.crop_x, saved.crop_y,
                     saved.crop_x + saved.crop_w, saved.crop_y + saved.crop_h),
            width=saved.width, height=saved.height)

        with self.assertNumQueries(2):
            apply_crops(image, [ThumbRequest(**request)])

        with self.assertNumQueries(1):
            result = apply_crops(image, [ThumbRequest(thumb=saved, **request)])

        self.assertIs(result.thumbs['no_height'], saved)

    def test_an_existing_crop_keeps_values_omitted_from_the_request(self):
        image = self.saved_image()
        saved = image.thumbs.get(name='no_height')

        result = apply_crops(image, [ThumbRequest(
            name='no_height', size=NO_HEIGHT, thumb_id=saved.pk)])

        thumb = result.thumbs['no_height']
        self.assertEqual(thumb.pk, saved.pk)
        self.assertEqual(
            (thumb.width, thumb.height), (saved.width, saved.height))
        self.assertEqual(thumb.get_crop_box(), saved.get_crop_box())
        self.assertTrue(result.outcomes[0].copied)

    def test_a_pending_recrop_with_an_image_id_keeps_its_tmp_rendition(self):
        image = self.saved_image()
        saved = image.thumbs.get(name='no_height')
        new_box = Box(10, 10, 810, 650)

        cropped = apply_crops(image, [ThumbRequest(
            name='no_height', size=NO_HEIGHT, thumb_id=saved.pk,
            crop=new_box, width=600, height=480, changed=True)])
        pending = cropped.thumbs['no_height']
        self.assertIsNotNone(pending.image_id)

        tmp_path = image.get_image_path('no_height', tmp=True)
        with image.storage.open(tmp_path) as f:
            pending_rendition = f.read()

        request = ThumbRequest(
            name='no_height', size=NO_HEIGHT, thumb_id=pending.pk,
            crop=new_box, width=pending.width, height=pending.height)
        result = apply_crops(image, [request])

        self.assertFalse(result.outcomes[0].copied)
        self.assertTrue(result.outcomes[0].tmp)
        with image.storage.open(tmp_path) as f:
            self.assertEqual(f.read(), pending_rendition)

    def test_an_uncropped_size_is_answered_with_a_suggestion(self):
        result = apply_crops(self.image, [
            ThumbRequest(name='main', size=MAIN, crop=Box(15, 0, 1285, 1016),
                         changed=True),
            ThumbRequest(name='no_height', size=NO_HEIGHT),
        ], pil_image=self.source())

        self.assertEqual(list(result.suggestions), ['no_height'])
        self.assertNotIn('no_height', result.thumbs)
        self.assertIsNone(result.outcomes[1].thumb.pk)

        suggestion = result.suggestions['no_height']
        self.assertEqual(suggestion, result.outcomes[1].suggestion)
        # Taken from the first size that was cropped.
        self.assertEqual(suggestion.as_tuple(), (15, 0, 1285, 1016))

    def test_nothing_to_suggest_from(self):
        result = apply_crops(
            self.image, [ThumbRequest(name='no_height', size=NO_HEIGHT)],
            pil_image=self.source())

        self.assertEqual(result.suggestions, {})
        self.assertEqual(result.thumbs, {})

    def test_outcomes_line_up_with_the_requests(self):
        requests = [
            ThumbRequest(name='main', size=MAIN, crop=Box(0, 0, 1200, 960),
                         changed=True),
            ThumbRequest(name='no_height', size=NO_HEIGHT),
        ]
        result = apply_crops(self.image, requests, pil_image=self.source())

        self.assertEqual([o.request for o in result.outcomes], requests)
        self.assertTrue(result.outcomes[0].changed)
        self.assertEqual(sorted(result.outcomes[0].created), ['main', 'thumb'])
        self.assertFalse(result.outcomes[1].changed)

    def test_renders_to_the_saved_names_when_not_temporary(self):
        image = self.saved_image()

        apply_crops(image, [ThumbRequest(
            name='main', size=MAIN, crop=Box(0, 0, 1200, 960), changed=True)],
            tmp=False)

        self.assertTrue(image.storage.exists(image.get_image_path('main')))

    def test_unchanged_crop_is_not_copied_when_not_temporary(self):
        image = self.saved_image()
        saved = image.thumbs.get(name='no_height')

        result = apply_crops(image, [ThumbRequest(
            name='no_height', size=NO_HEIGHT, thumb_id=saved.pk,
            crop=Box(saved.crop_x, saved.crop_y,
                     saved.crop_x + saved.crop_w,
                     saved.crop_y + saved.crop_h),
            width=saved.width, height=saved.height)], tmp=False)

        self.assertFalse(result.outcomes[0].copied)
        self.assertFalse(result.outcomes[0].tmp)
        self.assertFalse(image.storage.exists(
            image.get_image_path('no_height', tmp=True)))


class TestApplyCropsSources(CropServiceTestCase):
    """Restrict ``ThumbRequest.source`` to the image being cropped.

    The request format reserves this value for per-crop source overrides, but
    5.0 does not implement them.
    """

    def test_the_image_itself_may_be_named(self):
        result = apply_crops(self.image, [ThumbRequest(
            name='main', size=MAIN, crop=Box(0, 0, 1200, 960), changed=True,
            source=self.image.name)])

        self.assertEqual(sorted(result.thumbs), ['main', 'thumb'])

    def test_any_other_source_is_refused(self):
        other = self.create_unique_image('img.jpg')

        with self.assertRaises(NotImplementedError) as caught:
            apply_crops(self.image, [ThumbRequest(
                name='main', size=MAIN, crop=Box(0, 0, 600, 480), changed=True,
                source=other)])

        self.assertIn(other, str(caught.exception))

    def test_the_source_is_opened_once(self):
        opened = []
        real_open = crop_service.open_stored_image

        def counting_open(name, *, storage=None):
            opened.append(name)
            return real_open(name, storage=storage)

        crop_service.open_stored_image = counting_open
        self.addCleanup(
            setattr, crop_service, 'open_stored_image', real_open)

        apply_crops(self.image, [
            ThumbRequest(name='main', size=MAIN, crop=Box(0, 0, 1200, 960),
                         changed=True),
            ThumbRequest(name='no_height', size=NO_HEIGHT),
        ])

        self.assertEqual(opened, [self.image.name])

    def test_missing_original_can_still_produce_a_suggestion(self):
        image = Image(
            image='missing/original.jpg', width=1200, height=960)

        result = apply_crops(image, [
            ThumbRequest(
                name='main', size=MAIN,
                crop=Box(0, 0, 1200, 960)),
            ThumbRequest(name='no_height', size=NO_HEIGHT),
        ])

        self.assertEqual(
            result.suggestions['no_height'], Box(0, 0, 1200, 960))


class TestApplyCropsStandalone(CropServiceTestCase):

    def test_the_crop_is_named_after_its_contents(self):
        image = self.saved_image()

        result = apply_crops(image, [ThumbRequest(
            name='crop', size=Size('crop'), crop=Box(0, 0, 400, 300), changed=True)],
            standalone=True)

        thumb = result.outcomes[0].thumb
        self.assertEqual(len(thumb.name), 9)
        self.assertEqual(result.thumbs, {thumb.name: thumb})
        self.assertEqual(result.changed, {thumb.name})
        self.assertEqual((thumb.width, thumb.height), (400, 300))
        self.assertTrue(image.storage.exists(image.get_image_path(thumb.name)))
        self.assertFalse(result.outcomes[0].tmp)
        self.assertEqual(result.tmp_names, set())
        self.assertFalse(image.storage.exists(
            image.get_image_path(thumb.name, tmp=True)))
