import dataclasses
import os

from django import test
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.db import connection, transaction
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from cropduster import views
from cropduster.models import Image, Thumb
from cropduster.renderers import FileRenderer
from cropduster.services.payload import build_payload
from cropduster.utils import json
from cropduster.views.forms import CropForm
from cropduster.views.utils import FakeQuerySet

from .helpers import CropdusterTestCaseMediaMixin
from .models import Article


class TestFakeQuerySet(test.SimpleTestCase):

    def test_iterates(self):
        objs = [Thumb(name='a'), Thumb(name='b')]
        fake = FakeQuerySet(objs, Thumb.objects.none())
        self.assertEqual([t.name for t in fake], ['a', 'b'])

    def test_iterating_twice_restarts(self):
        fake = FakeQuerySet([Thumb(name='a')], Thumb.objects.none())
        self.assertEqual(len(list(fake)), 1)
        self.assertEqual(len(list(fake)), 1)

    def test_len_and_getitem(self):
        objs = [Thumb(name='a'), Thumb(name='b')]
        fake = FakeQuerySet(objs, Thumb.objects.none())
        self.assertEqual(len(fake), 2)
        self.assertIs(fake[1], objs[1])


class TestCropFormCleanSizes(test.SimpleTestCase):

    def test_returns_the_parsed_sizes(self):
        form = CropForm({
            'sizes': json.dumps([{'__type__': 'Size', 'name': 'main', 'w': 100, 'h': 50}]),
        })
        self.assertTrue(form.is_valid(), form.errors)
        sizes = form.cleaned_data['sizes']
        self.assertEqual([s.name for s in sizes], ['main'])

    def test_unparseable_sizes_become_an_empty_list(self):
        form = CropForm({'sizes': 'not json'})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['sizes'], [])


class TestCropViewSizes(CropdusterTestCaseMediaMixin, test.TestCase):

    def setUp(self):
        super(TestCropViewSizes, self).setUp()
        self.factory = test.RequestFactory()
        self.user = User.objects.create_superuser('test', 'test@test.com', 'password')

    def upload(self, sizes_json):
        with open(os.path.join(self.TEST_IMG_DIR, 'img.jpg'), 'rb') as img_file:
            request = self.factory.post(reverse('cropduster-upload'), {
                'image': img_file,
                'upload_to': 'test',
                'sizes': sizes_json,
            })
        request.user = self.user
        return json.loads(views.upload(request).content)

    def test_response_echoes_the_submitted_sizes(self):
        """Return the parsed size list in ``crop.sizes``.

        ``CropForm.clean_sizes()`` previously parsed the submitted value and
        then discarded it, which made the response field null. Returning the
        posted sizes is the only intentional response change in this backend
        refactor.
        """
        sizes_json = json.dumps([{
            '__type__': 'Size', 'name': 'main', 'label': 'Main',
            'w': 200, 'h': 100, 'min_w': 200, 'min_h': 100,
            'max_w': None, 'max_h': None, 'retina': 0, 'required': True,
        }])
        uploaded = self.upload(sizes_json)

        request = self.factory.post(reverse('cropduster-crop'), {
            'crop-image_id': '',
            'crop-orig_image': uploaded['orig_image'],
            'crop-orig_w': uploaded['orig_w'],
            'crop-orig_h': uploaded['orig_h'],
            'crop-sizes': sizes_json,
            'crop-thumbs': '{}',
            'thumbs-TOTAL_FORMS': '1',
            'thumbs-INITIAL_FORMS': '0',
            'thumbs-MIN_NUM_FORMS': '0',
            'thumbs-MAX_NUM_FORMS': '1000',
            'thumbs-0-id': '',
            'thumbs-0-name': 'main',
            'thumbs-0-width': '200',
            'thumbs-0-height': '100',
            'thumbs-0-crop_x': '0',
            'thumbs-0-crop_y': '0',
            'thumbs-0-crop_w': '400',
            'thumbs-0-crop_h': '200',
            'thumbs-0-changed': 'on',
            'thumbs-0-size': sizes_json[1:-1],
            'thumbs-0-thumbs': '{}',
        })
        request.user = self.user
        response = views.crop(request)
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertNotIn('error', data)
        self.assertEqual([s.name for s in data['crop']['sizes']], ['main'])


class CountingRenderer(FileRenderer):
    """Record each crop URL requested from the configured renderer."""

    calls = []

    def url(self, thumb, **opts):
        type(self).calls.append(('url', getattr(thumb, 'name', None)))
        return super(CountingRenderer, self).url(thumb, **opts)

    def srcset(self, thumb, **opts):
        type(self).calls.append(('srcset', getattr(thumb, 'name', None)))
        return super(CountingRenderer, self).srcset(thumb, **opts)


class CropViewTestCase(CropdusterTestCaseMediaMixin, test.TestCase):
    """Create a saved image and a request that replaces one crop."""

    SIZE = Article.LEAD_IMAGE_SIZES[1]

    def setUp(self):
        super(CropViewTestCase, self).setUp()
        self.factory = test.RequestFactory()
        self.user = User.objects.create_superuser('test', 'test@test.com', 'password')

        article = Article.objects.create(
            title='Cropped', lead_image=self.create_unique_image('img2.jpg'))
        article.lead_image.generate_thumbs()
        self.image = Image.objects.get(
            content_type=ContentType.objects.get_for_model(Article),
            object_id=article.pk, field_identifier='')
        self.thumb = self.image.thumbs.get(name=self.SIZE.name)

    def crop_request(self, **crop_box):
        """Return a POST with crop coordinates different from the saved row."""
        box = dict(
            crop_x=self.thumb.crop_x, crop_y=self.thumb.crop_y,
            crop_w=self.thumb.crop_w - 10, crop_h=self.thumb.crop_h - 10)
        box.update(crop_box)
        request = self.factory.post(reverse('cropduster-crop'), dict({
            'crop-image_id': str(self.image.pk),
            'crop-orig_image': self.image.name,
            'crop-orig_w': str(self.image.width),
            'crop-orig_h': str(self.image.height),
            'crop-sizes': json.dumps([self.SIZE]),
            'crop-thumbs': '{}',
            'thumbs-TOTAL_FORMS': '1',
            'thumbs-INITIAL_FORMS': '1',
            'thumbs-MIN_NUM_FORMS': '0',
            'thumbs-MAX_NUM_FORMS': '1000',
            'thumbs-0-id': str(self.thumb.pk),
            'thumbs-0-name': self.thumb.name,
            'thumbs-0-width': str(self.thumb.width),
            'thumbs-0-height': str(self.thumb.height),
            'thumbs-0-size': json.dumps(self.SIZE),
            'thumbs-0-thumbs': '{}',
        }, **{'thumbs-0-%s' % key: str(value) for key, value in box.items()}))
        request.user = self.user
        return request

    def assertCropped(self, response):
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertNotIn('error', data)
        self.assertEqual(sorted(data['crop']['thumbs']), [self.SIZE.name])
        return data


class TestCropViewRendererUse(CropViewTestCase):
    """Do not call the renderer while building a legacy crop response.

    That response uses stored-file URLs. Calling a Thumbor renderer would sign
    URLs that no response field uses.
    """

    @test.override_settings(
        CROPDUSTER_URL_RENDERER='tests.test_views_regressions.CountingRenderer')
    def test_a_crop_post_asks_the_renderer_for_nothing(self):
        CountingRenderer.calls = []

        self.assertCropped(views.crop(self.crop_request()))

        self.assertEqual(CountingRenderer.calls, [])

    @test.override_settings(
        CROPDUSTER_URL_RENDERER='tests.test_views_regressions.CountingRenderer')
    def test_the_canonical_payload_does_ask_for_them(self):
        """Confirm that ``build_payload`` does call the renderer."""
        CountingRenderer.calls = []

        build_payload(self.image)

        self.assertIn(('url', self.SIZE.name), CountingRenderer.calls)
        self.assertIn(('srcset', self.SIZE.name), CountingRenderer.calls)


class TestCropViewQueries(CropViewTestCase):

    def test_the_thumbs_the_formset_loaded_are_not_loaded_again(self):
        """Pass rows loaded by the formset directly to the crop service.

        Each initial form already loaded its ``Thumb`` row. Looking it up again
        would add one query per crop.
        """
        savepoint = transaction.savepoint()
        with CaptureQueriesContext(connection) as preloaded:
            self.assertCropped(views.crop(self.crop_request()))
        transaction.savepoint_rollback(savepoint)

        thumb_request = views._thumb_request

        def without_the_loaded_row(*args):
            return dataclasses.replace(thumb_request(*args), thumb=None)

        views._thumb_request = without_the_loaded_row
        self.addCleanup(setattr, views, '_thumb_request', thumb_request)

        with CaptureQueriesContext(connection) as looked_up:
            self.assertCropped(views.crop(self.crop_request()))

        self.assertEqual(
            len(looked_up.captured_queries) - len(preloaded.captured_queries), 1)
