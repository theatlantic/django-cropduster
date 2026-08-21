from django import test
from django.contrib.contenttypes.models import ContentType

from cropduster.models import Image, Thumb
from cropduster.resizing import Box, Crop, Size
from cropduster.services.crops import choose_crop, crop_overlap, thumb_for_size

from .helpers import CropdusterTestCaseMediaMixin
from .models import Article


MAIN = Size('main', w=600, h=480)
SQUARE = Size('square', w=400, h=400)
TALL = Size('tall', w=300, h=600)
AUTO_PARENT = Size('main', w=600, h=480, auto=[Size('thumb', w=110, h=90)])


def crop(x, y, w, h, image_size=(674, 800)):
    return Crop(Box(x, y, x + w, y + h), image_size)


class TestCropOverlap(test.SimpleTestCase):

    def test_identical_crops_overlap_entirely(self):
        self.assertEqual(crop_overlap(crop(0, 0, 100, 100), crop(0, 0, 100, 100)), 1.0)

    def test_disjoint_crops_do_not_overlap(self):
        self.assertEqual(crop_overlap(crop(0, 0, 100, 100), crop(200, 0, 100, 100)), 0.0)

    def test_crops_that_only_touch_do_not_overlap(self):
        self.assertEqual(crop_overlap(crop(0, 0, 100, 100), crop(100, 0, 100, 100)), 0.0)

    def test_partial_overlap_is_intersection_over_union(self):
        # 50x100 of intersection, 150x100 of union.
        self.assertAlmostEqual(
            crop_overlap(crop(0, 0, 100, 100), crop(50, 0, 100, 100)), 1 / 3)

    def test_a_contained_crop_overlaps_by_its_share_of_the_area(self):
        self.assertAlmostEqual(
            crop_overlap(crop(0, 0, 100, 100), crop(0, 0, 50, 50)), 0.25)


class BestCropTestCase(CropdusterTestCaseMediaMixin, test.TestCase):
    """Create a saved image for crop-selection tests."""

    def setUp(self):
        super(BestCropTestCase, self).setUp()
        self.article = Article.objects.create(title='Framed')
        self.image = Image.objects.create(
            image=self.create_unique_image('img.jpg'),
            width=674, height=800,
            content_type=ContentType.objects.get_for_model(Article),
            object_id=self.article.pk)

    def draw(self, name, x, y, w, h, **kwargs):
        return Thumb.objects.create(
            name=name, image=self.image, width=w, height=h,
            crop_x=x, crop_y=y, crop_w=w, crop_h=h, **kwargs)


class TestChooseCrop(BestCropTestCase):

    def test_an_image_with_no_crops_has_nothing_to_choose_from(self):
        self.assertIsNone(choose_crop(self.image, MAIN))

    def test_an_unsaved_image_has_nothing_to_choose_from(self):
        self.assertIsNone(choose_crop(Image(width=674, height=800), MAIN))

    def test_the_crop_whose_framing_survives_best_is_chosen(self):
        wide = self.draw('wide', 0, 0, 674, 400)
        self.draw('portrait', 0, 0, 300, 700)

        chosen = choose_crop(self.image, MAIN)

        self.assertEqual(chosen.box, wide.get_crop_box())

    def test_the_choice_is_made_per_size(self):
        self.draw('wide', 0, 0, 674, 400)
        portrait = self.draw('portrait', 0, 0, 300, 700)

        self.assertEqual(choose_crop(self.image, TALL).box, portrait.get_crop_box())

    def test_equally_good_crops_are_broken_by_taking_the_newest(self):
        self.draw('first', 0, 0, 500, 400)
        second = self.draw('second', 100, 100, 500, 400)

        chosen = choose_crop(self.image, MAIN)

        self.assertEqual(chosen.box, second.get_crop_box())

    def test_crops_with_no_box_are_not_candidates(self):
        Thumb.objects.create(name='legacy', image=self.image, width=100, height=100)

        self.assertIsNone(choose_crop(self.image, MAIN))

    def test_crops_with_an_empty_box_are_not_candidates(self):
        self.draw('empty', 0, 0, 0, 100)

        self.assertIsNone(choose_crop(self.image, MAIN))

    def test_candidates_may_be_given(self):
        self.draw('wide', 0, 0, 674, 400)
        given = crop(10, 20, 300, 300)

        self.assertIs(choose_crop(self.image, SQUARE, candidates=[given]), given)

    def test_a_hint_names_one_of_the_image_crops(self):
        self.draw('wide', 0, 0, 674, 400)
        portrait = self.draw('portrait', 0, 0, 300, 700)

        chosen = choose_crop(self.image, MAIN, hint='portrait')

        self.assertEqual(chosen.box, portrait.get_crop_box())

    def test_a_hint_may_be_a_thumb_a_box_or_a_tuple(self):
        portrait = self.draw('portrait', 0, 0, 300, 700)
        box = Box(0, 0, 300, 700)

        for hint in (portrait, box, (0, 0, 300, 700), Crop(box, (674, 800))):
            self.assertEqual(choose_crop(self.image, MAIN, hint=hint).box, box)

    def test_a_hint_naming_nothing_is_an_error(self):
        with self.assertRaises(ValueError):
            choose_crop(self.image, MAIN, hint='nope')

    def test_an_unreadable_hint_is_an_error(self):
        with self.assertRaises(ValueError):
            choose_crop(self.image, MAIN, hint=(1, 2, 3))


class TestThumbForSize(BestCropTestCase):

    def test_the_whole_frame_is_used_when_there_are_no_crops(self):
        thumb = thumb_for_size(self.image, MAIN)

        self.assertEqual(
            (thumb.crop_x, thumb.crop_y, thumb.crop_w, thumb.crop_h), (0, 130, 674, 539))
        self.assertEqual((thumb.width, thumb.height), (600, 480))
        self.assertEqual(thumb.image, self.image)

    def test_an_existing_crop_frames_the_new_size(self):
        """Fit the selected crop to the requested size."""
        self.draw('portrait', 0, 0, 300, 700)

        thumb = thumb_for_size(self.image, TALL)

        self.assertEqual(
            (thumb.crop_x, thumb.crop_y, thumb.crop_w, thumb.crop_h), (0, 26, 324, 648))
        self.assertEqual((thumb.width, thumb.height), (300, 600))

    def test_a_crop_may_be_supplied(self):
        thumb = thumb_for_size(self.image, SQUARE, best_crop=crop(300, 0, 374, 374))

        self.assertEqual(
            (thumb.crop_x, thumb.crop_y, thumb.crop_w, thumb.crop_h), (274, 0, 400, 400))
        self.assertEqual((thumb.width, thumb.height), (400, 400))

    def test_an_image_too_small_for_the_size_gets_no_thumb(self):
        self.assertIsNone(thumb_for_size(self.image, Size('huge', w=2000, h=1000)))
        self.assertIsNone(thumb_for_size(self.image, Size('tall', w=100, h=1000)))

    def test_a_crop_box_too_small_for_the_size_gets_no_thumb(self):
        """Return no thumb when clamping leaves too few pixels."""
        self.assertIsNone(
            thumb_for_size(self.image, MAIN, best_crop=crop(0, 0, 2000, 2000)))

    def test_an_auto_size_gets_no_crop_box_of_its_own(self):
        auto = AUTO_PARENT.auto[0]

        thumb = thumb_for_size(self.image, auto)

        self.assertEqual(thumb.name, 'thumb')
        self.assertEqual((thumb.width, thumb.height), (110, 90))
        self.assertEqual(
            (thumb.crop_x, thumb.crop_y, thumb.crop_w, thumb.crop_h),
            (None, None, None, None))

    def test_a_size_with_one_dimension_takes_the_other_from_the_box(self):
        thumb = thumb_for_size(self.image, Size('no_height', w=600))

        self.assertEqual((thumb.width, thumb.height), (600, 712))

    def test_maximum_dimensions_scale_the_output(self):
        thumb = thumb_for_size(
            Image(width=1000, height=800),
            Size('bounded', max_w=200, max_h=200))

        self.assertEqual((thumb.width, thumb.height), (200, 160))

    def test_the_crops_of_an_unsaved_image_are_orphans(self):
        thumb = thumb_for_size(Image(width=674, height=800), MAIN)

        self.assertIsNone(thumb.image)

    def test_dimensions_may_be_given_instead_of_being_read(self):
        """Calculate geometry from dimensions when no file is available."""
        image = Image(image='gone/original.jpg', width=674, height=800)

        thumb = thumb_for_size(image, MAIN)

        self.assertEqual(
            (thumb.crop_x, thumb.crop_y, thumb.crop_w, thumb.crop_h), (0, 130, 674, 539))

    def test_given_dimensions_override_the_image(self):
        thumb = thumb_for_size(self.image, MAIN, image_size=(1200, 600))

        self.assertEqual((thumb.crop_w, thumb.crop_h), (750, 600))


class TestBestThumbForSize(BestCropTestCase):

    def test_the_model_chooses_and_fits_in_one_call(self):
        self.draw('wide', 0, 0, 674, 400)
        self.draw('portrait', 0, 0, 300, 700)

        thumb = self.image.best_thumb_for_size(MAIN)

        self.assertEqual(
            (thumb.crop_x, thumb.crop_y, thumb.crop_w, thumb.crop_h), (37, 0, 600, 480))
        self.assertEqual((thumb.width, thumb.height), (600, 480))

    def test_a_hint_overrides_the_choice(self):
        self.draw('wide', 0, 0, 674, 400)
        self.draw('portrait', 0, 0, 300, 700)

        thumb = self.image.best_thumb_for_size(MAIN, hint='portrait')

        self.assertEqual(
            (thumb.crop_x, thumb.crop_y, thumb.crop_w, thumb.crop_h), (0, 110, 600, 480))

    def test_dimensions_may_be_given(self):
        thumb = Image().best_thumb_for_size(MAIN, image_size=(674, 800))

        self.assertEqual(
            (thumb.crop_x, thumb.crop_y, thumb.crop_w, thumb.crop_h), (0, 130, 674, 539))
