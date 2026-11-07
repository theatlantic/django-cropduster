import json as stdlib_json

from django import test
from django.contrib.contenttypes.models import ContentType

from cropduster.models import Image
from cropduster.renderers import BaseRenderer, get_renderer
from cropduster.resizing import Box, Size
from cropduster.services.crop import ThumbRequest, apply_crops
from cropduster.services.payload import build_payload, payload_to_legacy
from cropduster.services.upload import PreviewInfo

from .helpers import CropdusterTestCaseMediaMixin, FILESYSTEM_STORAGES
from .models import Article


MAIN = Size('main', w=600, h=480, auto=[Size('thumb', w=110, h=90)])
NO_HEIGHT = Size('no_height', w=600)


class StubRenderer(BaseRenderer):
    """Return renderer URLs that differ from stored-file URLs."""

    def url(self, thumb, **opts):
        return 'https://cdn.example.com/%s' % thumb.name

    def srcset(self, thumb, **opts):
        return 'https://cdn.example.com/%s 2x' % thumb.name

    def preview_url(self, image, **opts):
        return 'https://cdn.example.com/preview'

    def preview_srcset(self, image, *, width, height):
        return 'https://cdn.example.com/preview-2x 2x'

    def original_url(self, image, **opts):
        return 'https://cdn.example.com/original'


@test.override_settings(STORAGES=FILESYSTEM_STORAGES)
class PayloadTestCase(CropdusterTestCaseMediaMixin, test.TestCase):

    def setUp(self):
        super(PayloadTestCase, self).setUp()
        self.image_name = self.create_unique_image('img2.jpg')

    def saved_image(self, **kwargs):
        article = Article.objects.create(title='Payload', lead_image=self.image_name)
        article.lead_image.generate_thumbs()
        image = Image.objects.get(
            content_type=ContentType.objects.get_for_model(Article),
            object_id=article.pk, field_identifier='')
        for name, value in kwargs.items():
            setattr(image, name, value)
        if kwargs:
            image.save()
        return image


class TestBuildPayload(PayloadTestCase):

    def test_shape(self):
        payload = build_payload(self.saved_image())

        self.assertEqual(payload['version'], 1)
        self.assertEqual(sorted(payload), [
            'image', 'metadata', 'preview', 'sizes', 'thumbs', 'version', 'warnings'])

    def test_image_block(self):
        image = self.saved_image()
        payload = build_payload(image)

        self.assertEqual(payload['image'], {
            'id': image.pk,
            'name': image.name,
            'url': get_renderer().original_url(image),
            'width': image.width,
            'height': image.height,
            'field_identifier': '',
            'content_type_id': image.content_type_id,
            'object_id': image.object_id,
        })

    def test_thumbs_are_read_from_the_image_when_not_given(self):
        image = self.saved_image()

        payload = build_payload(image)

        self.assertEqual(sorted(payload['thumbs']), ['main', 'no_height', 'thumb'])

    def test_an_unsaved_image_has_no_crops_to_read(self):
        payload = build_payload(Image(image=self.image_name))

        self.assertEqual(payload['thumbs'], {})
        self.assertIsNone(payload['image']['id'])

    def test_a_crop_entry(self):
        image = self.saved_image()
        main = image.thumbs.get(name='main')

        entry = build_payload(image)['thumbs']['main']

        self.assertEqual(entry, {
            'id': main.pk,
            'name': 'main',
            'width': 600,
            'height': 480,
            'crop': {
                'x': main.crop_x, 'y': main.crop_y,
                'width': main.crop_w, 'height': main.crop_h,
            },
            'ref': None,
            'ref_id': None,
            'url': main.get_url(),
            'srcset': main.get_srcset(),
            'file_url': image.get_image_url('main'),
            'tmp': False,
            'changed': False,
            'source': None,
        })

    def test_an_auto_crop_names_the_crop_it_follows(self):
        image = self.saved_image()
        entry = build_payload(image)['thumbs']['thumb']

        self.assertIsNone(entry['crop'])
        self.assertEqual(entry['ref'], 'main')
        self.assertEqual(entry['ref_id'], image.thumbs.get(name='main').pk)

    def test_sizes_are_serialized_as_declared(self):
        payload = build_payload(self.saved_image(), sizes=[MAIN])

        self.assertEqual(payload['sizes'], [MAIN.__serialize__()])
        self.assertEqual(payload['sizes'][0]['__type__'], 'Size')

    def test_metadata(self):
        image = self.saved_image(
            attribution='A Photographer', attribution_link='https://example.com/',
            caption='A caption', alt_text='Alt')

        self.assertEqual(build_payload(image)['metadata'], {
            'attribution': 'A Photographer',
            'attribution_link': 'https://example.com/',
            'caption': 'A caption',
            'alt_text': 'Alt',
        })

    def test_preview_is_derived_when_not_given(self):
        image = self.saved_image()

        preview = build_payload(image)['preview']

        self.assertEqual(preview['url'], get_renderer().preview_url(image))
        # ``url`` contains the renderer result rather than the stored filename
        # used by legacy responses.
        self.assertNotEqual(preview['url'], image.get_image_url('_preview'))
        self.assertEqual((preview['width'], preview['height']), (640, 500))

    def test_the_preview_carries_its_file_as_well_as_its_url(self):
        """Include both renderer and stored-file URLs for the preview.

        The widget renders ``data-preview-url`` from the stored file, and the
        dialog reconstructs that attribute from the v1 payload.
        """
        image = self.saved_image()

        preview = build_payload(image, renderer=StubRenderer())['preview']

        self.assertEqual(preview['url'], 'https://cdn.example.com/preview')
        self.assertEqual(preview['file_url'], image.get_image_url('_preview'))
        self.assertEqual(
            preview['srcset'], 'https://cdn.example.com/preview-2x 2x')

    def test_an_unsaved_image_has_no_preview_file(self):
        preview = build_payload(Image())['preview']

        self.assertIsNone(preview['url'])
        self.assertIsNone(preview['file_url'])
        self.assertIsNone(preview['srcset'])

    def test_preview_may_be_stated(self):
        image = self.saved_image()

        payload = build_payload(
            image, preview=PreviewInfo(width=10, height=5),
            renderer=StubRenderer())

        self.assertEqual(payload['preview'], {
            'url': 'https://cdn.example.com/preview',
            'width': 10,
            'height': 5,
            'file_url': image.get_image_url('_preview'),
            'srcset': 'https://cdn.example.com/preview-2x 2x',
        })

    def test_preview_srcset_receives_the_reported_dimensions(self):
        seen = []

        class RecordingRenderer(StubRenderer):
            def preview_srcset(self, image, *, width, height):
                seen.append((width, height))
                return super(RecordingRenderer, self).preview_srcset(
                    image, width=width, height=height)

        build_payload(
            self.saved_image(),
            preview=PreviewInfo(width=640, height=500),
            renderer=RecordingRenderer())

        self.assertEqual(seen, [(640, 500)])

    def test_warnings_are_structured(self):
        payload = build_payload(self.saved_image(), warnings=[
            {'code': 'a_code', 'message': 'A message'}, 'a bare message'])

        self.assertEqual(payload['warnings'], [
            {'code': 'a_code', 'message': 'A message'},
            {'code': None, 'message': 'a bare message'},
        ])

    def test_urls_come_from_the_renderer(self):
        payload = build_payload(self.saved_image(), renderer=StubRenderer())

        self.assertEqual(payload['image']['url'], 'https://cdn.example.com/original')
        self.assertEqual(payload['preview']['url'], 'https://cdn.example.com/preview')
        self.assertEqual(
            payload['preview']['srcset'],
            'https://cdn.example.com/preview-2x 2x')
        self.assertEqual(payload['thumbs']['main']['url'], 'https://cdn.example.com/main')
        self.assertEqual(
            payload['thumbs']['main']['srcset'], 'https://cdn.example.com/main 2x')

    def test_the_renderer_is_handed_every_crop_at_once(self):
        """Pass all thumbs together so ``srcset`` does not repeat the query."""
        image = self.saved_image()
        seen = []

        class RecordingRenderer(StubRenderer):
            def url(self, thumb, *, thumbs=None, **opts):
                seen.append(thumbs)
                return super(RecordingRenderer, self).url(thumb, **opts)

        build_payload(image, renderer=RecordingRenderer())

        self.assertTrue(seen)
        for thumbs in seen:
            self.assertEqual(len(thumbs), 3)

    def test_a_crop_result_carries_its_changes_and_suggestions(self):
        image = Image(image=self.image_name)
        result = apply_crops(image, [
            ThumbRequest(name='main', size=MAIN, crop=Box(15, 0, 1285, 1016),
                         changed=True),
            ThumbRequest(name='no_height', size=NO_HEIGHT),
        ])

        payload = build_payload(image, thumbs=result, tmp=True)

        self.assertEqual(sorted(payload['thumbs']), ['main', 'no_height', 'thumb'])
        self.assertTrue(payload['thumbs']['main']['changed'])
        self.assertTrue(payload['thumbs']['main']['tmp'])

        suggested = payload['thumbs']['no_height']
        self.assertIsNone(suggested['id'])
        self.assertIsNone(suggested['url'])
        self.assertTrue(suggested['changed'])
        self.assertFalse(suggested['tmp'])
        self.assertEqual(suggested['crop'], {
            'x': 15, 'y': 0, 'width': 1270, 'height': 1016})

    def test_a_saved_crop_is_not_temporary(self):
        image = self.saved_image()

        payload = build_payload(image, tmp=True)

        self.assertFalse(payload['thumbs']['main']['tmp'])


class TestPayloadToLegacyUpload(PayloadTestCase):

    def test_upload_shape(self):
        image = Image(image=self.image_name)
        payload = build_payload(
            image, preview=PreviewInfo(width=640, height=500),
            warnings=[{'code': 'a_code', 'message': 'A message'}])

        legacy = payload_to_legacy(payload)

        self.assertEqual(legacy, {
            'warning': ['A message'],
            'crop': {
                'orig_image': image.name,
                'orig_w': 1300,
                'orig_h': 1016,
                'image_id': None,
            },
            'url': image.get_image_url('_preview'),
            'orig_image': image.name,
            'orig_w': 1300,
            'orig_h': 1016,
            'width': 1300,
            'height': 1016,
        })

    def test_standalone_upload_carries_the_crop_and_its_size(self):
        image = self.saved_image()
        thumb = image.save_size(Size('crop'), standalone=True, commit=False)
        size = Size('crop', w=200, h=100)

        legacy = payload_to_legacy(
            build_payload(image, thumbs=[thumb], sizes=[size]))

        self.assertEqual(legacy['crop']['image_id'], image.pk)
        self.assertEqual(
            stdlib_json.loads(legacy['crop']['sizes']), [size.__serialize__()])
        self.assertEqual(legacy['thumbs'], [{
            'crop_x': thumb.crop_x,
            'crop_y': thumb.crop_y,
            'crop_w': thumb.crop_w,
            'crop_h': thumb.crop_h,
            'width': thumb.width,
            'height': thumb.height,
            'id': None,
            'changed': True,
            'size': stdlib_json.dumps(size.__serialize__()),
            'name': thumb.name,
        }])


class TestPayloadToLegacyCrop(PayloadTestCase):

    def crop_result(self, image, requests):
        result = apply_crops(image, requests, tmp=True)
        payload = build_payload(image, thumbs=result, tmp=True)
        return result, payload

    def test_crop_shape(self):
        image = Image(image=self.image_name)
        result, payload = self.crop_result(image, [ThumbRequest(
            name='main', size=MAIN, crop=Box(15, 0, 1285, 1016), changed=True)])

        crop = {
            'image_id': None, 'orig_image': image.name, 'orig_w': 1300,
            'orig_h': 1016, 'sizes': [MAIN], 'thumbs': {}, 'standalone': False,
        }
        echo = [{
            'id': None, 'name': 'main', 'width': None, 'height': None,
            'crop_x': 15, 'crop_y': 0, 'crop_w': 1270, 'crop_h': 1016,
            'thumbs': {}, 'size': MAIN, 'changed': False,
        }]

        legacy = payload_to_legacy(payload, crop=crop, echo=echo, result=result)

        self.assertEqual(sorted(legacy), [
            'crop', 'initial', 'preview_h', 'preview_url', 'preview_w', 'thumbs'])
        self.assertIs(legacy['initial'], True)
        self.assertEqual(legacy['preview_url'], image.get_image_url('_preview'))
        self.assertEqual((legacy['preview_w'], legacy['preview_h']), (640, 500))

        main = result.thumbs['main']
        auto = result.thumbs['thumb']
        self.assertEqual(legacy['crop']['thumbs'], {
            'main': {
                'id': main.pk, 'name': 'main', 'width': 600, 'height': 480,
                'url': image.get_image_url('main', tmp=True),
            },
            'thumb': {
                'id': auto.pk, 'name': 'thumb', 'width': 110, 'height': 90,
                'url': image.get_image_url('thumb', tmp=True),
            },
        })

        entry = legacy['thumbs'][0]
        self.assertEqual(entry['id'], main.pk)
        self.assertTrue(entry['changed'])
        self.assertEqual((entry['width'], entry['height']), (600, 480))
        # The echoed URL uses the saved filename regardless of the renderer.
        self.assertEqual(entry['url'], image.get_image_url('main'))
        # An automatic crop is nested below its parent size.
        self.assertEqual(sorted(entry['thumbs']), ['main'])

    def test_a_suggestion_is_answered_without_a_crop(self):
        image = Image(image=self.image_name)
        result, payload = self.crop_result(image, [
            ThumbRequest(name='main', size=MAIN, crop=Box(15, 0, 1285, 1016),
                         changed=True),
            ThumbRequest(name='no_height', size=NO_HEIGHT),
        ])

        crop = {'orig_w': 1300, 'orig_h': 1016, 'thumbs': {}}
        echo = [
            {'id': None, 'name': 'main', 'thumbs': {}},
            {'id': None, 'name': 'no_height', 'thumbs': {}, 'width': None,
             'height': None},
        ]

        legacy = payload_to_legacy(payload, crop=crop, echo=echo, result=result)

        suggested = legacy['thumbs'][1]
        self.assertEqual(
            (suggested['crop_x'], suggested['crop_y'],
             suggested['crop_w'], suggested['crop_h']), (15, 0, 1270, 1016))
        self.assertTrue(suggested['changed'])
        self.assertIsNone(suggested['id'])
        self.assertNotIn('url', suggested)
        self.assertNotIn('no_height', legacy['crop']['thumbs'])

    def test_the_submitted_crops_are_left_where_they_are(self):
        """Preserve submitted data for sizes not rendered by this request."""
        image = Image(image=self.image_name)
        result, payload = self.crop_result(image, [ThumbRequest(
            name='main', size=MAIN, crop=Box(15, 0, 1285, 1016), changed=True)])

        submitted = {'id': 7, 'name': 'other', 'width': 1, 'height': 2}
        crop = {'orig_w': 1300, 'orig_h': 1016, 'thumbs': {'other': submitted}}

        legacy = payload_to_legacy(payload, crop=crop, echo=[{}], result=result)

        self.assertEqual(legacy['crop']['thumbs']['other'], submitted)

    def test_the_payload_carries_the_file_beside_the_renderer_url(self):
        """Keep the stored file URL beside the renderer URL.

        The dialog reconstructs a legacy response from the v1 payload and
        cannot derive a stored filename from an arbitrary renderer URL.
        """
        image = Image(image=self.image_name)
        result = apply_crops(image, [ThumbRequest(
            name='main', size=MAIN, crop=Box(15, 0, 1285, 1016), changed=True)],
            tmp=True)

        payload = build_payload(
            image, thumbs=result, tmp=True, renderer=StubRenderer())
        legacy = payload_to_legacy(
            payload, crop={'orig_w': 1300, 'orig_h': 1016, 'thumbs': {}},
            echo=[{'id': None, 'thumbs': {}}], result=result)

        entry = payload['thumbs']['main']
        self.assertEqual(entry['url'], 'https://cdn.example.com/main')
        self.assertEqual(entry['file_url'], image.get_image_url('main', tmp=True))
        self.assertEqual(entry['file_url'], legacy['crop']['thumbs']['main']['url'])

    def test_the_default_renderer_cache_busts_the_url_but_not_the_file(self):
        image = self.saved_image()

        entry = build_payload(image)['thumbs']['main']

        self.assertIn('?mod=', entry['url'])
        self.assertNotIn('?', entry['file_url'])
        self.assertEqual(entry['file_url'], image.get_image_url('main'))

    def test_a_suggested_crop_has_no_file_to_name(self):
        image = Image(image=self.image_name)
        result = apply_crops(image, [
            ThumbRequest(name='main', size=MAIN, crop=Box(15, 0, 1285, 1016),
                         changed=True),
            ThumbRequest(name='no_height', size=NO_HEIGHT),
        ], tmp=True)

        payload = build_payload(image, thumbs=result, tmp=True)

        self.assertIsNone(payload['thumbs']['no_height']['file_url'])
        self.assertIsNone(payload['thumbs']['no_height']['url'])

    def test_urls_are_files_even_when_the_renderer_addresses_them_elsewhere(self):
        image = Image(image=self.image_name)
        result = apply_crops(image, [ThumbRequest(
            name='main', size=MAIN, crop=Box(15, 0, 1285, 1016), changed=True)],
            tmp=True)
        payload = build_payload(
            image, thumbs=result, tmp=True, renderer=StubRenderer())

        legacy = payload_to_legacy(
            payload, crop={'orig_w': 1300, 'orig_h': 1016, 'thumbs': {}},
            echo=[{'id': None, 'thumbs': {}}], result=result)

        self.assertEqual(payload['thumbs']['main']['url'], 'https://cdn.example.com/main')
        self.assertEqual(
            legacy['crop']['thumbs']['main']['url'],
            image.get_image_url('main', tmp=True))
        self.assertEqual(legacy['preview_url'], image.get_image_url('_preview'))

    def test_sanitize_makes_the_crop_names_subscriptable(self):
        image = Image(image=self.image_name)
        retina = Size('main@2x', w=1200, h=960)
        result, payload = self.crop_result(image, [ThumbRequest(
            name='main@2x', size=retina, crop=Box(0, 0, 1200, 960), changed=True)])

        legacy = payload_to_legacy(
            payload, crop={'orig_w': 1300, 'orig_h': 1016, 'thumbs': {}},
            echo=[{'id': None, 'thumbs': {}}], result=result, sanitize=True)

        self.assertEqual(sorted(legacy['crop']['thumbs']), ['main_2x'])
        self.assertEqual(sorted(legacy['thumbs'][0]['thumbs']), ['main_2x'])

    def test_a_crop_the_formset_cleaned_into_an_object_is_reported_as_a_pk(self):
        image = self.saved_image()
        main = image.thumbs.get(name='main')
        payload = build_payload(image)

        legacy = payload_to_legacy(
            payload, crop={'orig_w': 1300, 'orig_h': 1016, 'thumbs': {}},
            echo=[{'id': main, 'name': 'main'}], result=None)

        self.assertEqual(legacy['thumbs'][0]['id'], main.pk)

    def test_the_preview_dimensions_are_the_bounds_for_an_image_that_fits(self):
        """Keep the preview-size cases shared with the frontend implementation.

        ``frontend/src/formset/legacyPayload.ts`` rebuilds this payload for the
        dialog. Its ``legacyPreviewSize`` must match ``_legacy_preview_size``
        because the widget stores these dimensions and uses them when rendering
        the thumbnail. ``cropduster/forms.py`` applies the same rule on initial
        page load, and ``legacyPayload.test.ts`` repeats this table.
        """
        cases = [
            ((700, 500), (800, 500)),
            ((800, 500), (800, 500)),
            ((1600, 1000), (800, 500)),
            ((1300, 1016), (640, 500)),
            ((674, 800), (421, 500)),
            ((None, None), (800, 500)),
            ((700, 0), (800, 500)),
        ]

        for (orig_w, orig_h), expected in cases:
            legacy = payload_to_legacy(
                build_payload(Image(image=self.image_name)),
                crop={'orig_w': orig_w, 'orig_h': orig_h, 'thumbs': {}},
                echo=[], result=None)

            self.assertEqual(
                (legacy['preview_w'], legacy['preview_h']), expected,
                "%sx%s" % (orig_w, orig_h))
