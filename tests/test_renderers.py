"""Check renderer selection and the file and Thumbor URL formats.

The expected Thumbor URLs are copied from a downstream CMS's serializer
tests, previously the only assertions for this format.
:class:`GoldenFixtureMixin` recreates that suite's 1240x800 original at
``z/blue/original.jpg`` and the same three crops.
"""

import datetime
import time
import unittest

from django.contrib.contenttypes.models import ContentType
from django.core.files.base import ContentFile
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings

from cropduster.exceptions import CropDusterConfigurationError
from cropduster.forms import CropDusterThumbWidget
from cropduster.models import Image, Thumb
from cropduster.renderers import (
    BaseRenderer, FileRenderer, ThumborRenderer, get_renderer)
from cropduster.renderers.thumbor import _warn_legacy_setting
from cropduster.resizing import Size
from cropduster.utils import json
from cropduster.views import CropDusterIndex

from .helpers import CropdusterTestCaseMediaMixin, FILESYSTEM_STORAGES
from .models import Author


try:
    import libthumbor
except ImportError:
    libthumbor = None

requires_libthumbor = unittest.skipUnless(
    libthumbor is not None, "libthumbor is not installed")


ORIGINAL_NAME = 'z/blue/original.jpg'

THUMBOR_SETTINGS = {
    'CROPDUSTER_URL_RENDERER': 'cropduster.renderers.ThumborRenderer',
    'MEDIA_URL': 'https://cdn.theatlantic.com/media/',
    'CROPDUSTER_THUMBOR': {
        'SERVER': 'https://thumb.org/',
        'MEDIA_URL': 'https://cdn.theatlantic.com/media/',
        'SECURITY_KEY': '',
    },
}

# Golden Thumbor URLs from the downstream serializer tests.
THUMB_1X = "https://thumb.org/unsafe/0x90:1240x710/300x150/media/z/blue/original.jpg"
THUMB_2X = "https://thumb.org/unsafe/0x90:1240x710/600x300/media/z/blue/original.jpg"
THUMB_4X = "https://thumb.org/unsafe/0x90:1240x710/1200x600/media/z/blue/original.jpg"
SQUARE_1X = "https://thumb.org/unsafe/220x0:1020x800/400x400/media/z/blue/original.jpg"
SQUARE_2X = "https://thumb.org/unsafe/220x0:1020x800/media/z/blue/original.jpg"

THUMB_SRCSET = "%s, %s 2x" % (THUMB_1X, THUMB_2X)
THUMB_2X_SRCSET = "%s, %s 2x" % (THUMB_2X, THUMB_4X)
SQUARE_SRCSET = "%s, %s 2x" % (SQUARE_1X, SQUARE_2X)


class GoldenFixtureMixin(CropdusterTestCaseMediaMixin):
    """Recreate the downstream serializer fixture from crop geometry.

    The tests do not write an image file. Each renderer reads the dimensions
    and crop boxes from model rows, and storage returns the same URL whether
    or not the named file exists.
    """

    def setUp(self):
        super(GoldenFixtureMixin, self).setUp()
        author = Author.objects.create(name="Yves Klein")
        self.image = Image.objects.create(
            content_type=ContentType.objects.get_for_model(Author),
            object_id=author.pk,
            image=ORIGINAL_NAME,
            width=1240,
            height=800,
            attribution='Yves Klein',
            attribution_link='http://example.com/',
            caption='Blue is the color of blueberries.',
            alt_text='IKB 191, a monochromatic painting by Yves Klein')
        self.thumb = Thumb.objects.create(
            image=self.image, name='thumb', width=300, height=150,
            crop_x=0, crop_y=90, crop_w=1240, crop_h=620)
        self.thumb_2x = Thumb.objects.create(
            image=self.image, name='thumb@2x', width=600, height=300,
            reference_thumb=self.thumb)
        self.square = Thumb.objects.create(
            image=self.image, name='square', width=400, height=400,
            crop_x=220, crop_y=0, crop_w=800, crop_h=800)

    def mod(self, thumb):
        return int(time.mktime(thumb.date_modified.timetuple()))


class TestRendererSelection(SimpleTestCase):

    def test_default_is_the_file_renderer(self):
        self.assertIsInstance(get_renderer(), FileRenderer)

    @requires_libthumbor
    def test_dotted_path(self):
        with override_settings(
                CROPDUSTER_URL_RENDERER='cropduster.renderers.ThumborRenderer',
                CROPDUSTER_THUMBOR={
                    'SERVER': 'https://thumb.example.com/',
                }):
            self.assertIsInstance(get_renderer(), ThumborRenderer)

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

    @requires_libthumbor
    def test_an_unhashable_spec_is_built_but_not_cached(self):
        spec = {
            'BACKEND': 'cropduster.renderers.ThumborRenderer',
            'OPTIONS': {
                'server': 'https://thumb.example.com/',
                'extra_media_urls': {'https://cdn.example.com/media/'},
            },
        }
        with override_settings(CROPDUSTER_URL_RENDERER=spec):
            first, second = get_renderer(), get_renderer()

        self.assertIsInstance(first, ThumborRenderer)
        self.assertIsNot(first, second)

    def test_unimportable_backend(self):
        with override_settings(CROPDUSTER_URL_RENDERER='cropduster.renderers.Nope'):
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
    """Check ``srcset`` assembly independently of a renderer backend."""

    class Renderer(BaseRenderer):
        def __init__(self, urls):
            self.urls = urls

        def url(self, thumb, *, multiplier=1, **opts):
            return self.urls.get(multiplier)

    def test_first_density_is_bare_and_the_rest_are_labelled(self):
        renderer = self.Renderer({1: '/1x.jpg', 2: '/2x.jpg', 3: '/3x.jpg'})
        self.assertEqual(
            renderer.srcset(None, densities=(1, 2, 3)),
            '/1x.jpg, /2x.jpg 2x, /3x.jpg 3x')

    def test_densities_that_do_not_render_are_dropped(self):
        renderer = self.Renderer({1: '/1x.jpg', 2: None})
        self.assertEqual(renderer.srcset(None), '/1x.jpg')

    def test_none_when_1x_does_not_render(self):
        renderer = self.Renderer({1: None, 2: '/2x.jpg'})
        self.assertIsNone(renderer.srcset(None))

    def test_fractional_density(self):
        renderer = self.Renderer({1: '/1x.jpg', 1.5: '/1.5x.jpg'})
        self.assertEqual(
            renderer.srcset(None, densities=(1, 1.5)), '/1x.jpg, /1.5x.jpg 1.5x')


@override_settings(STORAGES=FILESYSTEM_STORAGES)
class TestFileRenderer(GoldenFixtureMixin, TestCase):

    def test_url_is_byte_identical_to_cache_safe_url(self):
        """``Thumb.cache_safe_url`` is read by downstream serializers.

        Routing it through a renderer must not change any part of the URL.
        """
        expected = "/media/z/blue/thumb.jpg?mod=%d" % self.mod(self.thumb)

        self.assertEqual(self.thumb.cache_safe_url, expected)
        self.assertEqual(self.thumb.get_url(), expected)
        self.assertEqual(FileRenderer().url(self.thumb), expected)

    def test_url_quotes_the_retina_name(self):
        self.assertEqual(
            self.thumb_2x.get_url(),
            "/media/z/blue/thumb%%402x.jpg?mod=%d" % self.mod(self.thumb_2x))

    def test_srcset_pairs_the_retina_sibling(self):
        self.assertEqual(self.thumb.get_srcset(), "%s, %s 2x" % (
            "/media/z/blue/thumb.jpg?mod=%d" % self.mod(self.thumb),
            "/media/z/blue/thumb%%402x.jpg?mod=%d" % self.mod(self.thumb_2x)))

    def test_srcset_is_just_the_url_when_there_is_no_sibling(self):
        self.assertEqual(
            self.square.get_srcset(),
            "/media/z/blue/square.jpg?mod=%d" % self.mod(self.square))

    def test_max_size_renders_as_1x(self):
        self.assertEqual(
            self.thumb.get_url(max_size=True), self.thumb.get_url())

    def test_tmp_addresses_the_pre_save_file(self):
        self.assertEqual(
            self.thumb.get_url(tmp=True),
            "/media/z/blue/thumb_tmp.jpg?mod=%d" % self.mod(self.thumb))

    def test_an_unsaved_image_addresses_the_pre_save_file(self):
        image = Image(image=ORIGINAL_NAME, width=1240, height=800)
        self.assertEqual(
            self.thumb.get_url(image=image),
            "/media/z/blue/thumb_tmp.jpg?mod=%d" % self.mod(self.thumb))

    def test_an_unsaved_image_has_no_siblings_to_pair(self):
        """An unsaved image's reverse relation is never read.

        Accessing it raises before the image is saved, so without an explicit
        ``thumbs`` list the renderer cannot find a 2x rendition.
        """
        image = Image(image=ORIGINAL_NAME, width=1240, height=800)

        self.assertIsNone(self.thumb.get_url(image=image, multiplier=2))

    def test_srcset_for_an_unsaved_image_is_the_1x_url(self):
        image = Image(image=ORIGINAL_NAME, width=1240, height=800)

        self.assertEqual(
            self.thumb.get_srcset(image=image),
            "/media/z/blue/thumb_tmp.jpg?mod=%d" % self.mod(self.thumb))

    def test_cache_buster_can_be_turned_off(self):
        self.assertEqual(
            FileRenderer(cache_buster=None).url(self.thumb), "/media/z/blue/thumb.jpg")

    def test_legacy_cache_buster_drops_the_fractional_seconds(self):
        self.assertEqual(
            FileRenderer(cache_buster='legacy').url(self.thumb),
            "/media/z/blue/thumb.jpg?%s" % str(
                time.mktime(self.thumb.date_modified.timetuple()))[:-2])

    def test_unknown_cache_buster(self):
        with self.assertRaises(CropDusterConfigurationError):
            FileRenderer(cache_buster='bogus')

    def test_an_unconfigured_cache_buster_leaves_the_templatetags_on_legacy(self):
        renderer = FileRenderer()

        self.assertEqual(renderer.cache_buster, 'mod')
        self.assertEqual(renderer.for_templatetag().cache_buster, 'legacy')

    def test_an_explicit_cache_buster_applies_to_the_templatetags_too(self):
        """An explicit cache-buster format also applies to the template tags.

        An explicit ``mod`` selects the same format for both call sites and
        must not be confused with the default value.
        """
        for value in ('mod', 'legacy', None):
            with self.subTest(cache_buster=value):
                renderer = FileRenderer(cache_buster=value)

                self.assertIs(renderer.for_templatetag(), renderer)
                self.assertEqual(renderer.for_templatetag().cache_buster, value)

    def test_original_and_preview(self):
        renderer = FileRenderer()
        mod = int(time.mktime(self.image.date_modified.timetuple()))
        self.assertEqual(
            renderer.original_url(self.image),
            "/media/z/blue/original.jpg?mod=%d" % mod)
        self.assertEqual(
            renderer.preview_url(self.image),
            "/media/z/blue/_preview.jpg?mod=%d" % mod)

    def test_preview_srcset_does_not_invent_a_file(self):
        self.assertIsNone(
            FileRenderer().preview_srcset(self.image, width=620, height=400))

    def test_does_not_support_metadata_only(self):
        self.assertIs(FileRenderer.supports_metadata_only, False)


class TestFindDensitySibling(GoldenFixtureMixin, TestCase):

    def test_exact_name_match(self):
        self.assertEqual(
            FileRenderer().find_density_sibling(self.thumb, 2), self.thumb_2x)

    def test_dimension_pairing_when_the_name_does_not_match(self):
        double = Thumb.objects.create(
            image=self.image, name='square_big', width=800, height=800,
            reference_thumb=self.square)

        self.assertEqual(
            FileRenderer().find_density_sibling(self.square, 2), double)

    def test_dimension_pairing_prefers_the_same_crop(self):
        """The larger thumb derived from the same crop box is preferred.

        Two thumbs may have equal dimensions but refer to different crops.
        """
        Thumb.objects.create(
            image=self.image, name='other_big', width=800, height=800,
            crop_x=0, crop_y=0, crop_w=800, crop_h=800)
        same_crop = Thumb.objects.create(
            image=self.image, name='square_big', width=800, height=800,
            reference_thumb=self.square)

        self.assertEqual(
            FileRenderer().find_density_sibling(self.square, 2), same_crop)

    def test_no_sibling(self):
        self.assertIsNone(FileRenderer().find_density_sibling(self.square, 2))

    def test_an_unsaved_thumb_list_pairs_by_name(self):
        """Unsaved thumbs are compared by identity rather than primary key.

        Every thumb in the list has a ``None`` primary key, so filtering by
        primary-key inequality would remove every candidate.
        """
        image = Image(image=ORIGINAL_NAME, width=1240, height=800)
        main = Thumb(name='main', width=300, height=150)
        retina = Thumb(name='main@2x', width=600, height=300)

        self.assertIs(
            FileRenderer().find_density_sibling(
                main, 2, image=image, thumbs=[main, retina]),
            retina)

    def test_an_unsaved_thumb_list_pairs_by_dimensions(self):
        image = Image(image=ORIGINAL_NAME, width=1240, height=800)
        main = Thumb(name='main', width=300, height=150)
        double = Thumb(name='big', width=600, height=300)

        self.assertIs(
            FileRenderer().find_density_sibling(
                main, 2, image=image, thumbs=[main, double]),
            double)

    def test_an_unsaved_image_without_a_thumb_list(self):
        image = Image(image=ORIGINAL_NAME, width=1240, height=800)

        self.assertIsNone(
            FileRenderer().find_density_sibling(self.thumb, 2, image=image))

    def test_a_prefetched_caller_pays_no_queries(self):
        image = Image.objects.with_thumbs().get(pk=self.image.pk)
        thumbs = {t.name: t for t in image.thumbs.all()}

        with self.assertNumQueries(0):
            thumbs['thumb'].get_srcset(image=image)

    def test_an_explicit_thumb_list_pays_no_queries(self):
        thumbs = list(Thumb.objects.filter(image=self.image))

        with self.assertNumQueries(0):
            self.thumb.get_srcset(image=self.image, thumbs=thumbs)


@requires_libthumbor
@override_settings(**THUMBOR_SETTINGS)
class TestThumborRendererGoldenUrls(GoldenFixtureMixin, TestCase):
    """Pin the Thumbor URLs copied from the downstream serializer tests."""

    def test_thumb(self):
        self.assertEqual(self.thumb.get_url(), THUMB_1X)
        self.assertEqual(self.thumb.get_srcset(), THUMB_SRCSET)

    def test_retina_thumb(self):
        self.assertEqual(self.thumb_2x.get_url(), THUMB_2X)
        self.assertEqual(self.thumb_2x.get_srcset(), THUMB_2X_SRCSET)

    def test_square(self):
        self.assertEqual(self.square.get_url(), SQUARE_1X)
        self.assertEqual(self.square.get_srcset(), SQUARE_SRCSET)

    def test_the_size_segment_is_dropped_when_it_equals_the_crop(self):
        """The size segment is omitted when the 2x size equals the crop box."""
        self.assertEqual(self.square.get_url(multiplier=2), SQUARE_2X)

    def test_cache_safe_url_follows_the_renderer(self):
        self.assertEqual(self.thumb.cache_safe_url, THUMB_1X)


@requires_libthumbor
@override_settings(**THUMBOR_SETTINGS)
class TestThumborRenderer(GoldenFixtureMixin, TestCase):

    def test_supports_metadata_only(self):
        self.assertIs(ThumborRenderer.supports_metadata_only, True)

    def test_never_upscales(self):
        """``url()`` returns ``None`` when a density exceeds the crop box.

        Callers use this result to omit unavailable higher-density candidates.
        """
        self.assertIsNone(self.square.get_url(multiplier=3))
        self.assertIsNone(self.thumb.get_url(multiplier=8))

    def test_a_density_the_crop_box_can_fill_renders(self):
        self.assertEqual(self.thumb_2x.get_url(multiplier=2), THUMB_4X)

    def test_max_size_renders_at_the_crop_box(self):
        self.assertEqual(
            self.thumb.get_url(max_size=True),
            "https://thumb.org/unsafe/0x90:1240x710/media/z/blue/original.jpg")

    def test_the_crop_segment_is_dropped_when_it_is_the_whole_original(self):
        full = Thumb.objects.create(
            image=self.image, name='full', width=620, height=400,
            crop_x=0, crop_y=0, crop_w=1240, crop_h=800)

        self.assertEqual(
            full.get_url(),
            "https://thumb.org/unsafe/620x400/media/z/blue/original.jpg")

    def test_same_sized_offset_crop_keeps_the_crop_segment(self):
        shifted = Thumb.objects.create(
            image=self.image, name='shifted', width=1240, height=800,
            crop_x=5, crop_y=0, crop_w=1240, crop_h=800)

        self.assertEqual(
            shifted.get_url(),
            "https://thumb.org/unsafe/5x0:1245x800"
            "/media/z/blue/original.jpg")

    def test_a_legacy_thumb_with_no_crop_box_renders_nothing(self):
        broken = Thumb.objects.create(image=self.image, name='legacy', width=1, height=1)

        self.assertIsNone(broken.get_url())

    def test_a_thumb_with_no_dimensions_has_no_2x(self):
        """A legacy row renders at 1x but not at a higher density.

        A row with null width and height can use its crop box for 1x, but has
        no dimensions to multiply for a density.
        """
        legacy = Thumb.objects.create(
            image=self.image, name='legacy', width=None, height=None,
            crop_x=0, crop_y=90, crop_w=1240, crop_h=620)

        self.assertIsNone(legacy.get_url(multiplier=2))
        self.assertIsNotNone(legacy.get_url())

    def test_a_reference_thumb_with_no_crop_box_renders_nothing(self):
        """A reference thumb whose source has no crop box renders nothing.

        A downstream implementation raised ``AttributeError`` here because it
        checked only top-level thumbs before ``get_crop_box()`` returned
        ``None``.
        """
        parent = Thumb.objects.create(image=self.image, name='parent', width=10, height=10)
        child = Thumb.objects.create(
            image=self.image, name='child', width=5, height=5, reference_thumb=parent)

        self.assertIsNone(child.get_url())

    def test_an_unsaved_thumb_renders_against_the_image_kwarg(self):
        thumb = Thumb(name='ad_hoc', width=300, height=150,
                      crop_x=0, crop_y=90, crop_w=1240, crop_h=620)

        self.assertEqual(thumb.get_url(image=self.image), THUMB_1X)

    def test_tmp_is_ignored(self):
        self.assertEqual(self.thumb.get_url(tmp=True), THUMB_1X)

    def test_original_url(self):
        self.assertEqual(
            self.image.get_url(),
            "https://thumb.org/unsafe/media/z/blue/original.jpg")

    def test_preview_url_fits_the_preview_box(self):
        self.assertEqual(
            self.image.get_url('preview'),
            "https://thumb.org/unsafe/fit-in/800x500/media/z/blue/original.jpg")

    def test_preview_srcset_uses_the_displayed_preview_dimensions(self):
        image = Image(image=ORIGINAL_NAME, width=1300, height=1016)

        self.assertEqual(
            ThumborRenderer().preview_srcset(image, width=640, height=500),
            "https://thumb.org/unsafe/fit-in/1280x1000/"
            "media/z/blue/original.jpg 2x")

    def test_preview_srcset_does_not_upscale(self):
        self.assertIsNone(
            ThumborRenderer().preview_srcset(
                self.image, width=640, height=500))

    def test_preview_srcset_requires_positive_dimensions(self):
        renderer = ThumborRenderer()
        for width, height in ((0, 500), (640, 0), (-1, 500), (640, -1)):
            with self.subTest(width=width, height=height):
                self.assertIsNone(
                    renderer.preview_srcset(
                        self.image, width=width, height=height))

    def test_image_get_url_by_size_name(self):
        self.assertEqual(self.image.get_url('square'), SQUARE_1X)
        self.assertIsNone(self.image.get_url('nonesuch'))

    def test_page_dialog_config_carries_renderer_urls_and_srcsets(self):
        self.image.width = 2480
        self.image.height = 1600
        self.image.save(update_fields=('width', 'height'))
        self.image.storage.save(
            self.image.get_image_path('_preview'), ContentFile(b'preview'))
        sizes = [
            Size('thumb', w=300, h=150, auto=[
                Size('thumb@2x', w=600, h=300)]),
            Size('square', w=400, h=400),
        ]
        request = RequestFactory().get('/cropduster/', {
            'id': self.image.pk,
            'thumbs': ','.join(str(thumb.pk) for thumb in (
                self.thumb, self.thumb_2x, self.square)),
            'sizes': json.dumps(sizes),
        })
        view = CropDusterIndex()
        view.request = request
        view.upload_to = None
        # This fixture asserts URL construction without writing source bytes.
        # Supply the dimensions the view would otherwise read from that file.
        view.__dict__['image'] = (
            ORIGINAL_NAME, self.image.width, self.image.height, self.image.pk)
        view.__dict__['db_image'] = self.image

        with self.assertNumQueries(1):
            config = view.dialog_config()

        self.assertEqual(
            config['preview']['url'], self.image.get_image_url('_preview'))
        self.assertEqual(
            config['preview']['rendererUrl'],
            'https://thumb.org/unsafe/fit-in/775x500/'
            'media/z/blue/original.jpg')
        self.assertEqual(
            config['preview']['srcset'],
            'https://thumb.org/unsafe/fit-in/1550x1000/'
            'media/z/blue/original.jpg 2x')
        self.assertEqual(config['thumbs'][0]['renderer_url'], THUMB_1X)
        self.assertEqual(config['thumbs'][0]['srcset'], THUMB_SRCSET)
        self.assertNotIn('renderer_url', config['cropThumbs']['thumb@2x'])
        self.assertNotIn('srcset', config['cropThumbs']['thumb@2x'])

    def test_a_signing_key_signs(self):
        renderer = ThumborRenderer(security_key='sesame')
        url = renderer.url(self.thumb, image=self.image)

        self.assertTrue(url.startswith('https://thumb.org/'))
        self.assertNotIn('/unsafe/', url)
        self.assertTrue(url.endswith('/0x90:1240x710/300x150/media/z/blue/original.jpg'))

    def test_filters_smart_and_fit_in(self):
        renderer = ThumborRenderer(filters=['quality(90)'], smart=True)

        self.assertEqual(
            renderer.url(self.thumb, image=self.image),
            "https://thumb.org/unsafe/0x90:1240x710/300x150/smart/filters:quality(90)"
            "/media/z/blue/original.jpg")

    def test_extra_options_reach_libthumbor(self):
        self.assertEqual(
            self.thumb.get_url(halign='left'),
            "https://thumb.org/unsafe/0x90:1240x710/300x150/left"
            "/media/z/blue/original.jpg")

    def test_no_server_configured(self):
        with self.assertRaises(CropDusterConfigurationError):
            ThumborRenderer(server='')

    def test_the_server_is_normalized_when_constructed(self):
        renderer = ThumborRenderer(server='https://thumb.example.com')

        self.assertEqual(renderer.server, 'https://thumb.example.com/')


@requires_libthumbor
class TestThumborSourcePrefix(GoldenFixtureMixin, TestCase):

    def render(self, **thumbor_settings):
        config = dict(THUMBOR_SETTINGS['CROPDUSTER_THUMBOR'], **thumbor_settings)
        with override_settings(
                CROPDUSTER_URL_RENDERER='cropduster.renderers.ThumborRenderer',
                CROPDUSTER_THUMBOR=config):
            return self.thumb.get_url()

    @override_settings(MEDIA_URL='https://cdn.theatlantic.com/media/')
    def test_thumbor_media_url_is_stripped(self):
        self.assertEqual(self.render(), THUMB_1X)

    @override_settings(MEDIA_URL='https://media.example.com/')
    def test_django_media_url_is_stripped_too(self):
        self.assertEqual(self.render(MEDIA_URL=None), THUMB_1X)

    @override_settings(MEDIA_URL='https://media.example.com/')
    def test_extra_media_urls_are_stripped(self):
        """The renderer also strips prefixes listed in ``EXTRA_MEDIA_URLS``.

        S3 may return files under a host different from the configured media
        URL.
        """
        url = self.render(
            MEDIA_URL='https://cdn.example.com/assets/media/',
            EXTRA_MEDIA_URLS=['https://media.example.com/'])

        self.assertEqual(url, THUMB_1X)

    def test_an_unrecognised_prefix_is_passed_through_whole(self):
        renderer = ThumborRenderer(
            server='https://thumb.org/', media_url='https://cdn.example.com/media/')

        self.assertEqual(
            renderer.strip_source_prefix('https://elsewhere.example.com/x.jpg'),
            'https://elsewhere.example.com/x.jpg')

    def test_an_absolute_source_url_keeps_its_scheme(self):
        """The scheme separator collapsed by ``urljoin`` is restored
        (bpo-40594)."""
        renderer = ThumborRenderer(
            server='https://thumb.org/', media_url='https://cdn.example.com/media/')

        self.assertEqual(
            renderer.image_url('https://elsewhere.example.com/x.jpg', width=10, height=10),
            "https://thumb.org/unsafe/10x10/https://elsewhere.example.com/x.jpg")

    def test_an_http_source_url_keeps_its_scheme_too(self):
        renderer = ThumborRenderer(
            server='https://thumb.org/', media_url='https://cdn.example.com/media/')

        self.assertEqual(
            renderer.image_url('http://elsewhere.example.com/x.jpg', width=10, height=10),
            "https://thumb.org/unsafe/10x10/http://elsewhere.example.com/x.jpg")

    @override_settings(MEDIA_URL='https://cdn.theatlantic.com/media/')
    def test_a_media_url_without_a_trailing_slash_is_read_as_one_with(self):
        self.assertEqual(
            self.render(MEDIA_URL='https://cdn.theatlantic.com/media'),
            self.render(MEDIA_URL='https://cdn.theatlantic.com/media/'))

    def test_the_stripped_path_has_no_doubled_slash(self):
        """``urljoin`` collapses one slash in the final URL, but the source
        path is passed to libthumbor before that occurs, so the strip itself
        must not leave a doubled slash.
        """
        renderer = ThumborRenderer(
            server='https://thumb.org/', media_url='https://cdn.example.com/media')

        self.assertEqual(
            renderer.strip_source_prefix('https://cdn.example.com/media/z/b.jpg'),
            'media/z/b.jpg')

    def test_an_extra_media_url_without_a_trailing_slash_is_read_as_one_with(self):
        renderer = ThumborRenderer(
            server='https://thumb.org/',
            media_url='https://cdn.example.com/media/',
            extra_media_urls=['https://s3.amazonaws.com/bucket/media'])

        self.assertEqual(
            renderer.strip_source_prefix('https://s3.amazonaws.com/bucket/media/z/b.jpg'),
            'media/z/b.jpg')

    def test_a_server_without_a_trailing_slash_keeps_its_path(self):
        """The last server path segment is kept where ``urljoin`` would drop
        it."""
        kwargs = {'media_url': 'https://cdn.example.com/media/'}
        bare = ThumborRenderer(server='https://cdn.example.com/thumbor', **kwargs)
        slashed = ThumborRenderer(server='https://cdn.example.com/thumbor/', **kwargs)
        source = 'https://cdn.example.com/media/z/blue/original.jpg'

        self.assertEqual(
            bare.image_url(source, width=10, height=10),
            "https://cdn.example.com/thumbor/unsafe/10x10/media/z/blue/original.jpg")
        self.assertEqual(
            bare.image_url(source, width=10, height=10),
            slashed.image_url(source, width=10, height=10))


@requires_libthumbor
class TestThumborConfiguration(SimpleTestCase):

    def test_a_non_text_security_key_is_a_configuration_error(self):
        """An integer key (seen in downstream settings) enables signing but
        then raises ``TypeError`` inside ``hmac``, so it is rejected at
        construction.
        """
        with override_settings(CROPDUSTER_THUMBOR={
                'SERVER': 'https://thumb.example.com/',
                'SECURITY_KEY': 5,
        }):
            with self.assertRaises(CropDusterConfigurationError):
                ThumborRenderer()

    def test_no_security_key_means_unsafe_urls(self):
        for key in (None, ''):
            with override_settings(CROPDUSTER_THUMBOR={
                    'SERVER': 'https://thumb.example.com/',
                    'SECURITY_KEY': key,
            }):
                self.assertFalse(ThumborRenderer().security_key)

    def test_bare_settings_are_read_with_a_deprecation_warning(self):
        _warn_legacy_setting.cache_clear()
        settings = {
            'THUMBOR_SERVER': 'https://thumb.example.com/',
            'THUMBOR_MEDIA_URL': 'https://cdn.example.com/media/',
            'THUMBOR_SECURITY_KEY': 'sesame',
        }
        with override_settings(**settings):
            with self.assertWarns(DeprecationWarning):
                renderer = ThumborRenderer()

        self.assertEqual(renderer.server, 'https://thumb.example.com/')
        self.assertEqual(renderer.media_url, 'https://cdn.example.com/media/')
        self.assertEqual(renderer.security_key, 'sesame')

    def test_the_settings_dict_wins_over_the_bare_settings(self):
        _warn_legacy_setting.cache_clear()
        with override_settings(
                THUMBOR_SERVER='https://legacy.example.com/',
                CROPDUSTER_THUMBOR={'SERVER': 'https://thumb.example.com/'}):
            self.assertEqual(ThumborRenderer().server, 'https://thumb.example.com/')

    def test_options_win_over_the_settings_dict(self):
        with override_settings(CROPDUSTER_THUMBOR={'SERVER': 'https://thumb.example.com/'}):
            renderer = ThumborRenderer(server='https://other.example.com/')

        self.assertEqual(renderer.server, 'https://other.example.com/')


@override_settings(STORAGES=FILESYSTEM_STORAGES)
class TestThumbWidgetOptionAttrs(GoldenFixtureMixin, TestCase):
    """The option attributes the change form renders for each crop.

    ``data-url`` contains the stored file URL, byte-identical to 4.x, because
    downstream scripts read renditions from that exact attribute. The widget's
    summary card displays ``data-renderer-url``, which routes through the
    configured renderer.
    """

    def attrs(self, thumb):
        return CropDusterThumbWidget().get_option_attrs(thumb)

    def test_data_url_is_the_bare_stored_file(self):
        self.assertEqual(
            self.attrs(self.thumb)['data-url'], '/media/z/blue/thumb.jpg')

    def test_file_renderer_url_carries_the_cache_buster(self):
        self.assertEqual(
            self.attrs(self.thumb)['data-renderer-url'],
            '/media/z/blue/thumb.jpg?mod=%d' % self.mod(self.thumb))

    def test_file_renderer_srcset_names_only_existing_crop_rows(self):
        self.assertEqual(
            self.attrs(self.thumb)['data-renderer-srcset'], "%s, %s 2x" % (
                '/media/z/blue/thumb.jpg?mod=%d' % self.mod(self.thumb),
                '/media/z/blue/thumb%%402x.jpg?mod=%d' % self.mod(self.thumb_2x)))

    def test_option_srcsets_load_siblings_once(self):
        widget = CropDusterThumbWidget()

        with self.assertNumQueries(1):
            widget.get_option_attrs(self.thumb)
            widget.get_option_attrs(self.thumb_2x)

    @requires_libthumbor
    def test_thumbor_url_is_the_renderer_url(self):
        with override_settings(**THUMBOR_SETTINGS):
            attrs = self.attrs(self.thumb)

        self.assertTrue(attrs['data-url'].endswith('/z/blue/thumb.jpg'))
        self.assertNotIn('thumb.org', attrs['data-url'])
        self.assertEqual(attrs['data-renderer-url'], THUMB_1X)
        self.assertEqual(attrs['data-renderer-srcset'], THUMB_SRCSET)

    @requires_libthumbor
    def test_a_thumb_the_renderer_cannot_serve_omits_the_attribute(self):
        bare = Thumb.objects.create(image=self.image, name='bare')
        with override_settings(**THUMBOR_SETTINGS):
            attrs = self.attrs(bare)

        self.assertNotIn('data-renderer-url', attrs)
        self.assertNotIn('data-renderer-srcset', attrs)
