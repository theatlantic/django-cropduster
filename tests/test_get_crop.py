"""Check ``get_crop`` and ``get_thumbs`` with ``FileRenderer``."""

import time

from django.contrib.contenttypes.models import ContentType
from django.template import Context, Template
from django.test import TestCase, override_settings

from cropduster.models import Image, Thumb
from cropduster.templatetags.cropduster_tags import get_crop, get_thumbs

from .helpers import CropdusterTestCaseMediaMixin, FILESYSTEM_STORAGES
from .models import AliasedSizes


class TagFixture(CropdusterTestCaseMediaMixin):

    def setUp(self):
        super().setUp()
        self.obj = AliasedSizes.objects.create(
            slug='blue', image='z/blue/original.jpg')
        self.image = Image.objects.create(
            content_type=ContentType.objects.get_for_model(AliasedSizes),
            object_id=self.obj.pk,
            image='z/blue/original.jpg',
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

    def legacy_mod(self, obj):
        return str(time.mktime(obj.date_modified.timetuple()))[:-2]


@override_settings(STORAGES=FILESYSTEM_STORAGES)
class TestGetCrop(TagFixture, TestCase):

    def test_url_keeps_the_template_tag_cache_buster(self):
        crop = get_crop(self.obj.image, 'main')
        self.assertEqual(
            crop['url'],
            '/media/z/blue/main.jpg?%s' % self.legacy_mod(self.main))
        self.assertNotEqual(crop['url'], self.main.cache_safe_url)

    def test_srcset_uses_the_retina_sibling(self):
        crop = get_crop(self.obj.image, 'main')
        self.assertEqual(crop['srcset'], '%s, %s 2x' % (
            '/media/z/blue/main.jpg?%s' % self.legacy_mod(self.main),
            '/media/z/blue/main%%402x.jpg?%s' % self.legacy_mod(self.main_2x)))

    def test_explicit_cache_buster_reaches_the_tag(self):
        spec = {
            'BACKEND': 'cropduster.renderers.FileRenderer',
            'OPTIONS': {'cache_buster': 'mod'},
        }
        with override_settings(CROPDUSTER_URL_RENDERER=spec):
            crop = get_crop(self.obj.image, 'main')
        self.assertIn('?mod=', crop['url'])

    def test_metadata_thumb_and_crop_are_included(self):
        crop = get_crop(self.obj.image, 'main')
        self.assertEqual((crop['width'], crop['height']), (600, 480))
        self.assertEqual(crop['attribution'], 'Yves Klein')
        self.assertEqual(crop['thumb'], self.main)
        self.assertEqual(crop['crop'], {
            'x1': 0, 'y1': 90, 'x2': 1200, 'y2': 1050,
            'width': 1200, 'height': 960,
        })

    def test_original_uses_the_image(self):
        crop = get_crop(self.obj.image, 'original')
        self.assertEqual(crop['thumb'], self.image)
        self.assertIsNone(crop['crop'])
        self.assertIn('/media/z/blue/original.jpg?', crop['url'])

    def test_unknown_or_missing_image(self):
        self.assertIsNone(get_crop(self.obj.image, 'nonesuch'))
        self.assertIsNone(get_crop(None, 'main'))

    def test_template_render(self):
        output = Template(
            "{% load cropduster_tags %}"
            "{% get_crop obj.image 'main' as img %}"
            '<img src="{{ img.url }}" srcset="{{ img.srcset }}">').render(
                Context({'obj': self.obj}))
        self.assertIn('src="/media/z/blue/main.jpg?', output)
        self.assertIn(' 2x"', output)


@override_settings(STORAGES=FILESYSTEM_STORAGES)
class TestGetThumbs(TagFixture, TestCase):

    def test_names_are_sanitized(self):
        thumbs = get_thumbs(self.obj.image)
        self.assertIn('main', thumbs)
        self.assertIn('main_2x', thumbs)
        self.assertNotIn('main@2x', thumbs)

    def test_aliases_are_applied(self):
        thumbs = get_thumbs(self.obj.image)
        self.assertEqual(thumbs['lead'], thumbs['main'])
        self.assertEqual(thumbs['boxes']['lead'], thumbs['main'])

    def test_colliding_names_keep_the_first_and_warn(self):
        Thumb.objects.create(
            image=self.image, name='main_2x', width=1200, height=960,
            reference_thumb=self.main)
        with self.assertWarns(RuntimeWarning):
            thumbs = get_thumbs(self.obj.image)
        self.assertEqual(thumbs['main_2x']['thumb'], self.main_2x)

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

    def test_prefetched_image_adds_no_queries(self):
        obj = AliasedSizes.objects.prefetch_related(
            'image__thumbs').get(pk=self.obj.pk)
        with self.assertNumQueries(0):
            get_thumbs(obj.image)

    def test_missing_image(self):
        self.assertEqual(get_thumbs(None), {})
