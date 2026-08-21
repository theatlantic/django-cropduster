"""Check ``FileRenderer`` output and renderer selection."""

import datetime
import time

from django.contrib.contenttypes.models import ContentType
from django.test import SimpleTestCase, TestCase, override_settings

from cropduster.exceptions import CropDusterConfigurationError
from cropduster.models import Image, Thumb
from cropduster.renderers import BaseRenderer, FileRenderer, get_renderer

from .helpers import CropdusterTestCaseMediaMixin, FILESYSTEM_STORAGES
from .models import Author


ORIGINAL_NAME = 'z/blue/original.jpg'


class RendererFixture(CropdusterTestCaseMediaMixin):

    def setUp(self):
        super().setUp()
        author = Author.objects.create(name='Yves Klein')
        self.image = Image.objects.create(
            content_type=ContentType.objects.get_for_model(Author),
            object_id=author.pk,
            image=ORIGINAL_NAME,
            width=1240,
            height=800)
        self.thumb = Thumb.objects.create(
            image=self.image, name='thumb', width=300, height=150,
            crop_x=0, crop_y=90, crop_w=1240, crop_h=620)
        self.thumb_2x = Thumb.objects.create(
            image=self.image, name='thumb@2x', width=600, height=300,
            reference_thumb=self.thumb)
        self.square = Thumb.objects.create(
            image=self.image, name='square', width=400, height=400,
            crop_x=220, crop_y=0, crop_w=800, crop_h=800)

    def mod(self, obj):
        return int(time.mktime(obj.date_modified.timetuple()))


class TestRendererSelection(SimpleTestCase):

    def test_default_is_the_file_renderer(self):
        self.assertIsInstance(get_renderer(), FileRenderer)

    def test_dict_spec_passes_options_to_the_backend(self):
        spec = {
            'BACKEND': 'cropduster.renderers.FileRenderer',
            'OPTIONS': {'cache_buster': None},
        }
        with override_settings(CROPDUSTER_URL_RENDERER=spec):
            self.assertIsNone(get_renderer().cache_buster)

    def test_instances_are_cached(self):
        self.assertIs(get_renderer(), get_renderer())

    def test_cache_is_dropped_on_setting_changed(self):
        renderer = get_renderer()
        with override_settings(CROPDUSTER_PREVIEW_WIDTH=1):
            pass
        self.assertIsNot(get_renderer(), renderer)

    def test_unimportable_backend(self):
        with override_settings(
                CROPDUSTER_URL_RENDERER='cropduster.renderers.Nope'):
            with self.assertRaises(CropDusterConfigurationError):
                get_renderer()

    def test_dict_without_a_backend(self):
        with override_settings(CROPDUSTER_URL_RENDERER={'OPTIONS': {}}):
            with self.assertRaises(CropDusterConfigurationError):
                get_renderer()

    def test_storage_queries_are_not_modified(self):
        url = 'https://bucket.example/image.jpg?X-Amz-Signature=signed'
        modified = datetime.datetime(2026, 1, 1)
        for cache_buster in ('mod', 'legacy'):
            with self.subTest(cache_buster=cache_buster):
                self.assertEqual(
                    FileRenderer(cache_buster)._add_cache_buster(url, modified),
                    url)


class TestSrcsetSemantics(SimpleTestCase):

    class Renderer(BaseRenderer):
        def __init__(self, urls):
            self.urls = urls

        def url(self, thumb, *, multiplier=1, **opts):
            return self.urls.get(multiplier)

    def test_densities_after_one_are_labelled(self):
        renderer = self.Renderer({1: '/1x.jpg', 2: '/2x.jpg', 3: '/3x.jpg'})
        self.assertEqual(
            renderer.srcset(None, densities=(1, 2, 3)),
            '/1x.jpg, /2x.jpg 2x, /3x.jpg 3x')

    def test_missing_higher_density_is_dropped(self):
        renderer = self.Renderer({1: '/1x.jpg', 2: None})
        self.assertEqual(renderer.srcset(None), '/1x.jpg')

    def test_missing_one_x_returns_none(self):
        renderer = self.Renderer({1: None, 2: '/2x.jpg'})
        self.assertIsNone(renderer.srcset(None))

    def test_fractional_density(self):
        renderer = self.Renderer({1: '/1x.jpg', 1.5: '/1.5x.jpg'})
        self.assertEqual(
            renderer.srcset(None, densities=(1, 1.5)),
            '/1x.jpg, /1.5x.jpg 1.5x')


@override_settings(STORAGES=FILESYSTEM_STORAGES)
class TestFileRenderer(RendererFixture, TestCase):

    def test_url_keeps_the_cache_safe_url_bytes(self):
        expected = '/media/z/blue/thumb.jpg?mod=%d' % self.mod(self.thumb)
        self.assertEqual(self.thumb.cache_safe_url, expected)
        self.assertEqual(self.thumb.get_url(), expected)

    def test_retina_name_is_quoted(self):
        self.assertEqual(
            self.thumb_2x.get_url(),
            '/media/z/blue/thumb%%402x.jpg?mod=%d' % self.mod(self.thumb_2x))

    def test_srcset_uses_the_retina_sibling(self):
        self.assertEqual(self.thumb.get_srcset(), '%s, %s 2x' % (
            '/media/z/blue/thumb.jpg?mod=%d' % self.mod(self.thumb),
            '/media/z/blue/thumb%%402x.jpg?mod=%d' % self.mod(self.thumb_2x)))

    def test_srcset_without_a_sibling_is_the_one_x_url(self):
        self.assertEqual(self.square.get_srcset(), self.square.get_url())

    def test_tmp_uses_the_pre_save_name(self):
        self.assertEqual(
            self.thumb.get_url(tmp=True),
            '/media/z/blue/thumb_tmp.jpg?mod=%d' % self.mod(self.thumb))

    def test_cache_buster_modes(self):
        self.assertEqual(
            FileRenderer(cache_buster=None).url(self.thumb),
            '/media/z/blue/thumb.jpg')
        self.assertEqual(
            FileRenderer(cache_buster='legacy').url(self.thumb),
            '/media/z/blue/thumb.jpg?%s' % str(
                time.mktime(self.thumb.date_modified.timetuple()))[:-2])

    def test_unknown_cache_buster(self):
        with self.assertRaises(CropDusterConfigurationError):
            FileRenderer(cache_buster='bogus')

    def test_original_and_preview(self):
        renderer = FileRenderer()
        modified = self.mod(self.image)
        self.assertEqual(
            renderer.original_url(self.image),
            '/media/z/blue/original.jpg?mod=%d' % modified)
        self.assertEqual(
            renderer.preview_url(self.image),
            '/media/z/blue/_preview.jpg?mod=%d' % modified)

    def test_file_renderer_needs_derivative_files(self):
        self.assertIs(FileRenderer.supports_metadata_only, False)


class TestDensitySibling(RendererFixture, TestCase):

    def test_exact_name_match(self):
        self.assertEqual(
            FileRenderer().find_density_sibling(self.thumb, 2), self.thumb_2x)

    def test_dimension_match_prefers_the_same_crop(self):
        Thumb.objects.create(
            image=self.image, name='other', width=800, height=800,
            crop_x=0, crop_y=0, crop_w=800, crop_h=800)
        same_crop = Thumb.objects.create(
            image=self.image, name='square_big', width=800, height=800,
            reference_thumb=self.square)
        self.assertEqual(
            FileRenderer().find_density_sibling(self.square, 2), same_crop)

    def test_unsaved_thumb_list_pairs_by_name(self):
        main = Thumb(name='main', width=300, height=150)
        retina = Thumb(name='main@2x', width=600, height=300)
        self.assertIs(
            FileRenderer().find_density_sibling(
                main, 2, thumbs=[main, retina]),
            retina)

    def test_prefetched_caller_adds_no_queries(self):
        image = Image.objects.with_thumbs().get(pk=self.image.pk)
        thumbs = {thumb.name: thumb for thumb in image.thumbs.all()}
        with self.assertNumQueries(0):
            thumbs['thumb'].get_srcset(image=image)
