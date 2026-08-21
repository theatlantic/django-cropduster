"""Check the ``get_crop`` and ``get_thumbs`` template tags.

With ``FileRenderer``, the exact URL returned by ``get_crop`` remains part of
the 4.x behavior. Existing templates and downstream caches depend on that URL,
including its cache-buster format.
"""

import time

from django.contrib.contenttypes.models import ContentType
from django.template import Context, Template
from django.test import TestCase, override_settings

from cropduster.models import Image, Thumb
from cropduster.templatetags.cropduster_tags import get_crop, get_thumbs

from .helpers import CropdusterTestCaseMediaMixin, FILESYSTEM_STORAGES
from .models import AliasedSizes
from .test_renderers import THUMBOR_SETTINGS, requires_libthumbor


ORIGINAL_NAME = 'z/blue/original.jpg'


class TagFixtureMixin(CropdusterTestCaseMediaMixin):

    def setUp(self):
        super(TagFixtureMixin, self).setUp()
        self.obj = AliasedSizes.objects.create(slug='blue', image=ORIGINAL_NAME)
        self.image = Image.objects.create(
            content_type=ContentType.objects.get_for_model(AliasedSizes),
            object_id=self.obj.pk,
            image=ORIGINAL_NAME,
            width=1240,
            height=800,
            attribution='Yves Klein',
            attribution_link='http://example.com/',
            caption='Blue is the color of blueberries.',
            alt_text='IKB 191, a monochromatic painting by Yves Klein')
        self.main = Thumb.objects.create(
            image=self.image, name='main', width=600, height=480,
            crop_x=0, crop_y=90, crop_w=1200, crop_h=960)
        self.main_2x = Thumb.objects.create(
            image=self.image, name='main@2x', width=1200, height=960,
            reference_thumb=self.main)
        self.obj = AliasedSizes.objects.get(pk=self.obj.pk)

    def legacy_cache_buster(self, thumb):
        return str(time.mktime(thumb.date_modified.timetuple()))[:-2]

    def mod_cache_buster(self, thumb):
        return int(time.mktime(thumb.date_modified.timetuple()))


@override_settings(STORAGES=FILESYSTEM_STORAGES)
class TestGetCrop(TagFixtureMixin, TestCase):

    def test_url_keeps_the_tags_own_cache_buster(self):
        """The template tag keeps its own cache-buster format.

        It uses the bare ``mktime`` value without its trailing ``.0``, while
        ``Thumb.cache_safe_url`` uses ``?mod=``. Existing callers depend on
        both formats.
        """
        crop = get_crop(self.obj.image, 'main')

        self.assertEqual(
            crop['url'],
            "/media/z/blue/main.jpg?%s" % self.legacy_cache_buster(self.main))
        self.assertNotEqual(crop['url'], self.main.cache_safe_url)

    def test_srcset_pairs_the_retina_sibling(self):
        crop = get_crop(self.obj.image, 'main')

        self.assertEqual(crop['srcset'], "%s, %s 2x" % (
            "/media/z/blue/main.jpg?%s" % self.legacy_cache_buster(self.main),
            "/media/z/blue/main%%402x.jpg?%s" % self.legacy_cache_buster(self.main_2x)))

    def test_an_explicitly_configured_cache_buster_reaches_the_tag(self):
        """An explicitly configured cache-buster format reaches the tag.

        With ``mod`` set, the template tag and ``Thumb.cache_safe_url``
        return the same format.
        """
        spec = {
            'BACKEND': 'cropduster.renderers.FileRenderer',
            'OPTIONS': {'cache_buster': 'mod'},
        }
        with override_settings(CROPDUSTER_URL_RENDERER=spec):
            crop = get_crop(self.obj.image, 'main')

        self.assertEqual(
            crop['url'],
            "/media/z/blue/main.jpg?mod=%d" % self.mod_cache_buster(self.main))
        self.assertEqual(crop['srcset'], "%s, %s 2x" % (
            crop['url'],
            "/media/z/blue/main%%402x.jpg?mod=%d" % self.mod_cache_buster(self.main_2x)))

    def test_a_cache_buster_can_be_turned_off_for_the_tag(self):
        spec = {
            'BACKEND': 'cropduster.renderers.FileRenderer',
            'OPTIONS': {'cache_buster': None},
        }
        with override_settings(CROPDUSTER_URL_RENDERER=spec):
            self.assertEqual(
                get_crop(self.obj.image, 'main')['url'], "/media/z/blue/main.jpg")

    def test_srcset_is_just_the_url_without_a_sibling(self):
        crop = get_crop(self.obj.image, 'main@2x')

        self.assertEqual(crop['srcset'], crop['url'])

    def test_metadata_is_always_included(self):
        crop = get_crop(self.obj.image, 'main')

        self.assertEqual(crop['width'], 600)
        self.assertEqual(crop['height'], 480)
        self.assertEqual(crop['attribution'], 'Yves Klein')
        self.assertEqual(crop['attribution_link'], 'http://example.com/')
        self.assertEqual(crop['caption'], 'Blue is the color of blueberries.')
        self.assertEqual(
            crop['alt_text'], 'IKB 191, a monochromatic painting by Yves Klein')

    def test_the_thumb_and_its_crop_box_are_exposed(self):
        crop = get_crop(self.obj.image, 'main')

        self.assertEqual(crop['thumb'], self.main)
        self.assertEqual(crop['crop'], {
            'x1': 0, 'y1': 90, 'x2': 1200, 'y2': 1050,
            'width': 1200, 'height': 960,
        })

    def test_an_auto_thumb_reports_the_crop_it_was_taken_from(self):
        self.assertEqual(
            get_crop(self.obj.image, 'main@2x')['crop'],
            get_crop(self.obj.image, 'main')['crop'])

    def test_original_falls_back_to_the_image(self):
        """``'original'`` returns the image itself; no ``Thumb`` row exists
        for it."""
        crop = get_crop(self.obj.image, 'original')

        self.assertEqual(
            crop['url'],
            "/media/z/blue/original.jpg?%s" % self.legacy_cache_buster(self.image))
        self.assertEqual(crop['srcset'], crop['url'])
        self.assertEqual(crop['width'], 1240)
        self.assertEqual(crop['height'], 800)
        self.assertEqual(crop['thumb'], self.image)
        self.assertIsNone(crop['crop'])

    def test_an_unknown_crop_name(self):
        self.assertIsNone(get_crop(self.obj.image, 'nonesuch'))

    def test_no_image(self):
        self.assertIsNone(get_crop(None, 'main'))
        self.assertIsNone(get_crop(AliasedSizes(slug='empty').image, 'main'))

    def test_unknown_kwargs_are_ignored(self):
        """Obsolete keyword arguments still present in templates are
        ignored."""
        self.assertEqual(
            get_crop(self.obj.image, 'main', attribution=1, retina=True),
            get_crop(self.obj.image, 'main'))

    def test_exact_size_is_deprecated(self):
        with self.assertWarns(DeprecationWarning):
            get_crop(self.obj.image, 'main', exact_size=True)

    def test_from_a_template(self):
        template = Template(
            "{% load cropduster_tags %}"
            "{% get_crop obj.image 'main' as img %}"
            "<img src=\"{{ img.url }}\" srcset=\"{{ img.srcset }}\" "
            "alt=\"{{ img.alt_text }}\">")

        html = template.render(Context({'obj': self.obj}))

        self.assertIn('src="/media/z/blue/main.jpg?', html)
        self.assertIn(' 2x"', html)


@requires_libthumbor
@override_settings(**THUMBOR_SETTINGS)
class TestGetCropWithThumbor(TagFixtureMixin, TestCase):

    def test_url_and_srcset_come_from_the_renderer(self):
        crop = get_crop(self.obj.image, 'main')

        self.assertEqual(
            crop['url'],
            "https://thumb.org/unsafe/0x90:1200x1050/600x480"
            "/media/z/blue/original.jpg")
        self.assertEqual(crop['srcset'], "%s, %s 2x" % (
            crop['url'],
            "https://thumb.org/unsafe/0x90:1200x1050/media/z/blue/original.jpg"))

    def test_no_cache_buster(self):
        self.assertNotIn('?', get_crop(self.obj.image, 'main')['url'])


@override_settings(STORAGES=FILESYSTEM_STORAGES)
class TestGetThumbs(TagFixtureMixin, TestCase):

    def test_every_crop_is_keyed_by_a_sanitized_name(self):
        thumbs = get_thumbs(self.obj.image)

        self.assertIn('main', thumbs)
        self.assertIn('main_2x', thumbs)
        self.assertNotIn('main@2x', thumbs)

    def test_each_crop_is_what_get_crop_returns(self):
        self.assertEqual(
            get_thumbs(self.obj.image)['main'], get_crop(self.obj.image, 'main'))

    def test_colliding_names_keep_the_first_and_warn(self):
        """Colliding sanitized names resolve in a fixed order.

        ``main@2x`` and ``main_2x`` produce the same key. The names are
        sorted so that database row order does not change which crop is
        returned.
        """
        Thumb.objects.create(
            image=self.image, name='main_2x', width=1200, height=960,
            reference_thumb=self.main)

        with self.assertWarns(RuntimeWarning) as caught:
            thumbs = get_thumbs(self.obj.image)

        self.assertEqual(thumbs['main_2x']['thumb'], self.main_2x)
        self.assertIn('main@2x', str(caught.warning))
        self.assertIn('main_2x', str(caught.warning))

    def test_size_aliases_are_applied(self):
        thumbs = get_thumbs(self.obj.image)

        self.assertEqual(thumbs['lead'], thumbs['main'])
        self.assertEqual(thumbs['boxes']['lead'], thumbs['main'])

    def test_the_images_own_metadata_is_included(self):
        thumbs = get_thumbs(self.obj.image)

        metadata = thumbs['metadata']
        self.assertEqual(metadata['attribution'], 'Yves Klein')
        self.assertEqual(metadata['attribution_link'], 'http://example.com/')
        self.assertEqual(metadata['caption'], 'Blue is the color of blueberries.')
        self.assertEqual(
            metadata['alt_text'],
            'IKB 191, a monochromatic painting by Yves Klein')

    def test_a_crop_named_like_metadata_is_not_replaced(self):
        attribution = Thumb.objects.create(
            image=self.image, name='attribution', width=100, height=100,
            crop_x=0, crop_y=0, crop_w=100, crop_h=100)

        thumbs = get_thumbs(self.obj.image)

        self.assertEqual(thumbs['attribution']['thumb'], attribution)
        self.assertEqual(thumbs['metadata']['attribution'], 'Yves Klein')

    def test_no_image(self):
        self.assertEqual(get_thumbs(None), {})
        self.assertEqual(get_thumbs(AliasedSizes(slug='empty').image), {})

    def test_one_query_for_a_prefetched_image(self):
        obj = AliasedSizes.objects.prefetch_related(
            'image__thumbs').get(pk=self.obj.pk)
        with self.assertNumQueries(0):
            get_thumbs(obj.image)

    def test_from_a_template(self):
        template = Template(
            "{% load cropduster_tags %}"
            "{% get_thumbs obj.image as thumbs %}"
            "<img src=\"{{ thumbs.main_2x.url }}\">")

        html = template.render(Context({'obj': self.obj}))

        self.assertIn('src="/media/z/blue/main%402x.jpg?', html)
