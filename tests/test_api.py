"""Tests for the v1 state, upload, and crop endpoints.

All three endpoints return the same payload shape. Errors use the same envelope
and the appropriate HTTP status. The endpoints enforce CSRF protection and call
the permission function configured by ``CROPDUSTER_API_PERMISSION``.

When a request includes a target field, the API reads its sizes and upload
directory from the model field. This prevents the client from lowering the
field's minimum dimensions.

The legacy endpoints remain CSRF-exempt while
``CROPDUSTER_LEGACY_CSRF_EXEMPT`` is true.
"""

import hashlib
import json as stdlib_json
import os
import warnings
from unittest import mock

from django import test
from django.conf import settings as django_settings
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.core.files.storage import default_storage
from django.middleware.csrf import get_token
from django.test import Client, override_settings
from django.urls import reverse

from cropduster import conf as cropduster_conf
from cropduster.conf import settings as cropduster_settings
from cropduster.models import Image, Thumb
from cropduster.resizing import Size
from cropduster.standalone import NOT_INSTALLED_MESSAGE

from .helpers import CropdusterTestCaseMediaMixin
from .models import Article


PAYLOAD_KEYS = [
    'image', 'metadata', 'preview', 'sizes', 'thumbs', 'version', 'warnings']

THUMB_KEYS = [
    'changed', 'crop', 'file_url', 'height', 'id', 'name', 'ref', 'ref_id',
    'source', 'srcset', 'tmp', 'url', 'width']

BIG = Size('big', w=2000, h=1600)
SMALL = Size('small', w=100, h=80)


def allow_anyone(request, target=None):
    """Permission callable that accepts every request."""


def refuse_everyone(request, target=None):
    """Permission callable that raises for every request."""
    raise PermissionDenied("Not today.")


def return_false(request, target=None):
    """Permission callable that rejects a request by returning false."""
    return False


def serialize(sizes):
    return [size.__serialize__() for size in sizes]


class ApiTestCase(CropdusterTestCaseMediaMixin, test.TestCase):

    def setUp(self):
        super(ApiTestCase, self).setUp()
        self.user = User.objects.create_superuser('test', 'test@test.com', 'password')
        self.client.force_login(self.user)

        self.state_url = reverse('cropduster-api-state')
        self.upload_url = reverse('cropduster-api-upload')
        self.crop_url = reverse('cropduster-api-crop')

    # -- requests ---------------------------------------------------------

    def get_state(self, client=None, **params):
        return (client or self.client).post(self.state_url, params)

    def post_upload(self, image='img2.jpg', client=None, **data):
        with open(os.path.join(self.TEST_IMG_DIR, image), 'rb') as f:
            data['image'] = f
            return (client or self.client).post(self.upload_url, data)

    def post_crop(self, body, client=None):
        return (client or self.client).post(
            self.crop_url, stdlib_json.dumps(body),
            content_type='application/json')

    # -- assertions -------------------------------------------------------

    def assertPayload(self, response):
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response['Content-Type'], 'application/json')
        payload = stdlib_json.loads(response.content)
        self.assertEqual(sorted(payload), PAYLOAD_KEYS)
        self.assertEqual(payload['version'], 1)
        return payload

    def assertError(self, response, status, code, field=None):
        self.assertEqual(response.status_code, status, response.content)
        self.assertEqual(response['Content-Type'], 'application/json')
        body = stdlib_json.loads(response.content)
        self.assertEqual(sorted(body), ['error'])
        self.assertEqual(sorted(body['error']), ['code', 'details', 'field', 'message'])
        self.assertEqual(body['error']['code'], code)
        self.assertTrue(body['error']['message'])
        if field is not None:
            self.assertEqual(body['error']['field'], field)
        return body['error']

    # -- fixtures ---------------------------------------------------------

    def article_image(self, image='img2.jpg'):
        """Create a saved article and render every declared size."""
        article = Article.objects.create(
            title='An article', lead_image=self.create_unique_image(image))
        article.lead_image.generate_thumbs()
        return article, Image.objects.get(
            content_type=ContentType.objects.get_for_model(Article),
            object_id=article.pk, field_identifier='')

    def uploaded(self, sizes=Article.LEAD_IMAGE_SIZES, **data):
        payload = self.assertPayload(
            self.post_upload(sizes=stdlib_json.dumps(serialize(sizes)), **data))
        return payload['image']

    def crop_body(self, image, sizes=Article.LEAD_IMAGE_SIZES, **thumbs):
        return {
            'image': {
                'name': image['name'],
                'width': image['width'],
                'height': image['height'],
            },
            'sizes': serialize(sizes),
            'thumbs': thumbs,
        }


class TestState(ApiTestCase):

    def test_a_protocol_relative_image_url_is_invalid(self):
        self.assertError(
            self.get_state(image='//example.com/photo.jpg'),
            400, 'invalid', field='image')

    def test_an_unattached_image_hydrates_from_the_file(self):
        name = self.create_unique_image('img2.jpg')

        payload = self.assertPayload(self.get_state(
            image=name, sizes=stdlib_json.dumps(serialize([SMALL]))))

        self.assertEqual(payload['image'], {
            'id': None,
            'name': name,
            'url': mock.ANY,
            'width': 1300,
            'height': 1016,
            'field_identifier': '',
            'content_type_id': None,
            'object_id': None,
        })
        self.assertEqual(payload['thumbs'], {})
        self.assertEqual(payload['sizes'], serialize([SMALL]))

    def test_a_saved_image_hydrates_with_its_crops(self):
        article, image = self.article_image()

        payload = self.assertPayload(self.get_state(id=image.pk))

        self.assertEqual(payload['image']['id'], image.pk)
        self.assertEqual(sorted(payload['thumbs']), ['main', 'no_height', 'thumb'])
        self.assertEqual(sorted(payload['thumbs']['main']), THUMB_KEYS)
        self.assertEqual(payload['thumbs']['main']['crop'], {
            'x': image.thumbs.get(name='main').crop_x,
            'y': image.thumbs.get(name='main').crop_y,
            'width': image.thumbs.get(name='main').crop_w,
            'height': image.thumbs.get(name='main').crop_h,
        })
        self.assertEqual(payload['thumbs']['thumb']['ref'], 'main')

    def test_named_crops_are_read_instead_of_the_images_own(self):
        """Use the crop rows named by the widget's bound formset."""
        article, image = self.article_image()
        main = image.thumbs.get(name='main')

        payload = self.assertPayload(self.get_state(id=image.pk, thumbs=str(main.pk)))

        self.assertEqual(sorted(payload['thumbs']), ['main'])

    def test_named_crops_from_another_image_are_not_returned(self):
        _article, image = self.article_image()
        _other_article, other_image = self.article_image()
        other = other_image.thumbs.get(name='main')

        payload = self.assertPayload(self.get_state(
            id=image.pk, thumbs=str(other.pk),
            sizes=stdlib_json.dumps(serialize(Article.LEAD_IMAGE_SIZES))))

        returned_ids = {
            thumb['id'] for thumb in payload['thumbs'].values()
            if thumb['id'] is not None}
        self.assertNotIn(other.pk, returned_ids)

    def test_a_size_with_no_crop_is_answered_with_a_suggestion(self):
        article, image = self.article_image()
        image.thumbs.filter(name='no_height').delete()

        payload = self.assertPayload(self.get_state(
            id=image.pk,
            sizes=stdlib_json.dumps(serialize(Article.LEAD_IMAGE_SIZES))))

        suggested = payload['thumbs']['no_height']
        self.assertIsNone(suggested['id'])
        self.assertIsNone(suggested['url'])
        self.assertTrue(suggested['changed'])
        self.assertEqual(sorted(suggested['crop']), ['height', 'width', 'x', 'y'])

    def test_a_crop_is_not_suggested_for_a_size_that_has_one(self):
        article, image = self.article_image()

        payload = self.assertPayload(self.get_state(
            id=image.pk,
            sizes=stdlib_json.dumps(serialize(Article.LEAD_IMAGE_SIZES))))

        self.assertEqual(payload['thumbs']['no_height']['id'],
                         image.thumbs.get(name='no_height').pk)

    def test_a_different_filename_means_a_new_image(self):
        """A replacement filename starts a new image instead of reusing crops."""
        article, image = self.article_image()
        replacement = self.create_unique_image('img.jpg')

        payload = self.assertPayload(self.get_state(id=image.pk, image=replacement))

        self.assertIsNone(payload['image']['id'])
        self.assertEqual(payload['image']['name'], replacement)
        self.assertEqual(
            (payload['image']['width'], payload['image']['height']),
            (674, 800))

    def test_the_same_filename_is_the_same_image(self):
        article, image = self.article_image()

        payload = self.assertPayload(
            self.get_state(id=image.pk, image=image.image.name))

        self.assertEqual(payload['image']['id'], image.pk)

    def test_an_unknown_id_is_treated_as_a_new_image(self):
        payload = self.assertPayload(self.get_state(id='123456'))

        self.assertIsNone(payload['image']['id'])
        self.assertIsNone(payload['image']['name'])

    def test_the_preview_is_written_if_it_is_missing(self):
        article, image = self.article_image()
        image.storage.delete(image.get_image_path('_preview'))

        payload = self.assertPayload(self.get_state(id=image.pk))

        self.assertTrue(image.storage.exists(image.get_image_path('_preview')))
        self.assertTrue(payload['preview']['url'])
        self.assertEqual(
            (payload['preview']['width'], payload['preview']['height']), (640, 500))

    def test_a_preview_write_failure_is_an_invalid_image(self):
        _article, image = self.article_image()
        image.storage.delete(image.get_image_path('_preview'))

        with mock.patch.object(
                Image, 'save_preview', side_effect=OSError('not readable')):
            response = self.get_state(id=image.pk)

        error = self.assertError(
            response, 400, 'invalid_image', field='image')
        self.assertIn('not readable', error['message'])
        self.assertFalse(image.storage.exists(image.get_image_path('_preview')))

    def test_the_preview_box_can_be_asked_for(self):
        article, image = self.article_image()

        payload = self.assertPayload(
            self.get_state(id=image.pk, preview_size='300x300'))

        self.assertEqual(
            (payload['preview']['width'], payload['preview']['height']), (300, 234))

    def test_max_w_narrows_the_sizes_without_touching_the_declared_ones(self):
        article, image = self.article_image()

        payload = self.assertPayload(self.get_state(
            id=image.pk, max_w='400',
            sizes=stdlib_json.dumps(serialize(Article.LEAD_IMAGE_SIZES))))

        self.assertEqual(payload['sizes'][0]['max_w'], 400)
        self.assertIsNone(Article.LEAD_IMAGE_SIZES[0].max_w)

    def test_max_w_wider_than_the_image_is_ignored(self):
        article, image = self.article_image()

        payload = self.assertPayload(self.get_state(
            id=image.pk, max_w='4000',
            sizes=stdlib_json.dumps(serialize(Article.LEAD_IMAGE_SIZES))))

        self.assertIsNone(payload['sizes'][0]['max_w'])

    def test_a_preview_size_that_is_not_a_box(self):
        self.assertError(
            self.get_state(preview_size='wide'), 400, 'invalid', field='preview_size')

    def test_sizes_that_are_not_json(self):
        self.assertError(self.get_state(sizes='{{'), 400, 'invalid', field='sizes')

    def test_sizes_that_are_not_sizes(self):
        self.assertError(
            self.get_state(sizes='[{"name": "main"}]'), 400, 'invalid', field='sizes')


class TestPathsThatLeaveStorage(ApiTestCase):
    """Return path-traversal errors as invalid requests.

    Django rejects paths outside the storage root. Since these paths come from
    request data, the API returns a 400 error envelope without logging a server
    error.
    """

    def test_an_image_path_that_climbs_out(self):
        with self.assertNoLogs('cropduster', level='ERROR'):
            response = self.get_state(image='../../../../etc/passwd')

        self.assertError(response, 400, 'invalid')

    def test_an_upload_to_that_climbs_out(self):
        with self.assertNoLogs('cropduster', level='ERROR'):
            response = self.post_upload(upload_to='../../../../../../tmp/x')

        self.assertError(response, 400, 'invalid')


class StubOpener:
    """Return fixed contents and record each URL passed to ``urlopen``."""

    def __init__(self, contents):
        self.contents = contents
        self.urls = []

    def __call__(self, url):
        self.urls.append(url)
        return self

    def read(self):
        return self.contents


class TestRemoteImageFetch(ApiTestCase):
    """Test storage of images downloaded from request-supplied URLs.

    This behavior is retained for compatibility with the 4.x dialog.
    ``CROPDUSTER_REMOTE_IMAGE_FETCH`` disables it for projects that do not want
    the server to request user-supplied URLs.
    """

    def setUp(self):
        super(TestRemoteImageFetch, self).setUp()
        with open(os.path.join(self.TEST_IMG_DIR, 'img2.jpg'), 'rb') as f:
            self.opener = StubOpener(f.read())

    def test_a_url_is_fetched_and_stored_by_default(self):
        url = 'https://example.com/remote/photo.jpg'

        with mock.patch('cropduster.files.urlopen', self.opener):
            payload = self.assertPayload(self.get_state(image=url, upload_to='remote'))

        self.assertEqual(self.opener.urls, [url])
        self.assertTrue(payload['image']['name'].startswith('remote/photo'))
        self.assertEqual(
            (payload['image']['width'], payload['image']['height']), (1300, 1016))

    @override_settings(CROPDUSTER_REMOTE_IMAGE_FETCH=False)
    def test_a_url_is_refused_when_the_fetch_is_turned_off(self):
        with mock.patch('cropduster.files.urlopen', self.opener):
            response = self.get_state(
                image='https://example.com/remote/photo.jpg', upload_to='remote')

        error = self.assertError(response, 400, 'invalid')
        self.assertIn('CROPDUSTER_REMOTE_IMAGE_FETCH', error['message'])
        self.assertEqual(self.opener.urls, [], "nothing should have been fetched")

    @override_settings(CROPDUSTER_REMOTE_IMAGE_FETCH=False)
    def test_the_legacy_dialog_is_gated_by_the_same_setting(self):
        with mock.patch('cropduster.files.urlopen', self.opener):
            response = self.client.get(
                reverse('cropduster-index'),
                {'image': 'https://example.com/remote/photo.jpg'})

        # Legacy endpoints return HTTP 200 with an HTML error in the ``error``
        # property. Retain that response format for compatibility.
        self.assertEqual(response.status_code, 200)
        body = stdlib_json.loads(response.content)
        self.assertIn('CROPDUSTER_REMOTE_IMAGE_FETCH', body['error'])
        self.assertEqual(self.opener.urls, [])


class TestUpload(ApiTestCase):

    def test_upload_answers_the_canonical_payload(self):
        payload = self.assertPayload(self.post_upload(
            upload_to='test', sizes=stdlib_json.dumps(serialize([SMALL]))))

        self.assertIsNone(payload['image']['id'])
        self.assertTrue(payload['image']['name'].startswith('test/'))
        self.assertEqual(
            (payload['image']['width'], payload['image']['height']), (1300, 1016))
        self.assertEqual(payload['thumbs'], {})
        self.assertEqual(payload['sizes'], serialize([SMALL]))
        self.assertTrue(payload['preview']['url'])

    def test_an_image_too_small_for_its_sizes_names_both_dimensions(self):
        response = self.post_upload(
            'img.jpg', sizes=stdlib_json.dumps(serialize([BIG])))

        error = self.assertError(response, 400, 'image_too_small', field='image')
        self.assertEqual(error['details'], {'min': [2000, 1600], 'actual': [674, 800]})

    def test_for_size_narrows_the_minimum_to_one_size(self):
        sizes = stdlib_json.dumps(serialize([BIG, SMALL]))

        self.assertError(
            self.post_upload('img.jpg', sizes=sizes), 400, 'image_too_small')
        self.assertPayload(
            self.post_upload('img.jpg', sizes=sizes, for_size='small'))

    def test_for_size_naming_a_size_that_was_not_declared(self):
        self.assertError(
            self.post_upload(sizes=stdlib_json.dumps(serialize([SMALL])),
                             for_size='nope'),
            400, 'unknown_size', field='for_size')

    def test_an_upload_with_no_file(self):
        self.assertError(
            self.client.post(self.upload_url, {}), 400, 'invalid', field='image')

    def test_a_file_that_is_not_an_image(self):
        with open(__file__, 'rb') as f:
            response = self.client.post(self.upload_url, {'image': f})

        self.assertError(response, 400, 'invalid_image', field='image')

    def test_a_declared_md5_is_checked_before_anything_is_stored(self):
        response = self.post_upload(md5='0' * 32)

        error = self.assertError(response, 400, 'md5_mismatch', field='md5')
        self.assertEqual(error['details']['expected'], '0' * 32)
        self.assertEqual(Image.objects.count(), 0)
        self.assertEqual(default_storage.listdir('')[0], [])

    def test_a_matching_md5_is_accepted(self):
        with open(os.path.join(self.TEST_IMG_DIR, 'img2.jpg'), 'rb') as f:
            md5 = hashlib.md5(f.read()).hexdigest()

        self.assertPayload(self.post_upload(md5=md5))

    def test_a_standalone_upload_carries_the_rows_that_mode_needs(self):
        payload = self.assertPayload(self.post_upload(
            standalone='true', sizes=stdlib_json.dumps(serialize([Size('crop')]))))

        # A standalone upload creates its StandaloneImage row before returning,
        # so the response includes the image id.
        self.assertIsNotNone(payload['image']['id'])
        self.assertEqual(len(payload['thumbs']), 1)

        thumb = next(iter(payload['thumbs'].values()))
        self.assertEqual(
            thumb['crop'], {'x': 0, 'y': 0, 'width': 1300, 'height': 1016})

    def test_standalone_without_the_extra_is_refused_actionably(self):
        with mock.patch('cropduster.standalone.standalone_available',
                        return_value=False):
            response = self.post_upload(standalone='true')

        error = self.assertError(
            response, 501, 'standalone_unavailable', field='standalone')
        self.assertIn(NOT_INSTALLED_MESSAGE, error['message'])


class TestCrop(ApiTestCase):

    def test_the_upload_to_crop_round_trip(self):
        image = self.uploaded()

        payload = self.assertPayload(self.post_crop(self.crop_body(
            image,
            main={
                'id': None,
                'crop': {'x': 15, 'y': 0, 'width': 1270, 'height': 1016},
                'width': 600, 'height': 480,
                'changed': True,
                'source': None,
            },
            no_height={'id': None, 'crop': None, 'changed': False})))

        # Rendering ``main`` also renders its dependent ``thumb`` auto size.
        self.assertEqual(sorted(payload['thumbs']), ['main', 'no_height', 'thumb'])

        main = payload['thumbs']['main']
        self.assertEqual(sorted(main), THUMB_KEYS)
        self.assertEqual((main['width'], main['height']), (600, 480))
        self.assertTrue(main['changed'])
        self.assertTrue(main['tmp'])
        self.assertTrue(main['url'])
        self.assertIsNone(main['source'])

        self.assertEqual(payload['thumbs']['thumb']['ref'], 'main')

        # ``no_height`` has no crop box, so it is suggested but not rendered.
        suggested = payload['thumbs']['no_height']
        self.assertIsNone(suggested['id'])
        self.assertIsNone(suggested['url'])
        self.assertEqual(suggested['crop'],
                         {'x': 15, 'y': 0, 'width': 1270, 'height': 1016})

    def test_an_existing_crop_may_be_recropped(self):
        article, image = self.article_image()
        main = image.thumbs.get(name='main')

        payload = self.assertPayload(self.post_crop({
            'image': {'id': image.pk},
            'sizes': serialize(Article.LEAD_IMAGE_SIZES),
            'thumbs': {
                'main': {
                    'id': main.pk,
                    'crop': {'x': 0, 'y': 0, 'width': 1200, 'height': 960},
                    'width': 600, 'height': 480,
                    'changed': True,
                },
            },
        }))

        self.assertEqual(payload['image']['id'], image.pk)
        # Recropping creates a new row. The saved row remains until form save.
        self.assertNotEqual(payload['thumbs']['main']['id'], main.pk)
        self.assertEqual(payload['thumbs']['main']['crop'],
                         {'x': 0, 'y': 0, 'width': 1200, 'height': 960})

    def test_a_recrop_is_answered_with_the_temporary_file_it_wrote(self):
        """Return the temporary rendition created by recropping a saved image.

        Recropping clones the saved Thumb row without changing the saved
        rendition. The response must include the temporary file's URL so the
        dialog can redraw the crop.
        """
        article, image = self.article_image()
        main = image.thumbs.get(name='main')
        storage = image.storage
        saved_path = image.get_image_path('main')
        with storage.open(saved_path) as f:
            saved_before = f.read()

        payload = self.assertPayload(self.post_crop({
            'image': {'id': image.pk},
            'sizes': serialize(Article.LEAD_IMAGE_SIZES),
            'thumbs': {
                'main': {
                    'id': main.pk,
                    'crop': {'x': 0, 'y': 0, 'width': 1200, 'height': 960},
                    'width': 600, 'height': 480,
                    'changed': True,
                },
            },
        }))

        entry = payload['thumbs']['main']
        self.assertTrue(entry['tmp'])
        self.assertTrue(
            entry['url'].split('?')[0].endswith('main_tmp.jpg'), entry['url'])

        tmp_path = image.get_image_path('main', tmp=True)
        self.assertTrue(storage.exists(tmp_path), tmp_path)
        with storage.open(tmp_path) as f:
            rendered = f.read()
        with storage.open(saved_path) as f:
            saved_after = f.read()
        self.assertNotEqual(rendered, saved_after, "the new crop was not rendered")
        self.assertEqual(
            saved_after, saved_before,
            "the saved crop is not replaced until the form is saved")

        # The dependent auto crop also uses a temporary rendition.
        self.assertTrue(payload['thumbs']['thumb']['tmp'])

    def test_an_orphan_crop_with_this_images_tmp_file_may_be_reused(self):
        image = self.uploaded()
        first = self.assertPayload(self.post_crop(self.crop_body(
            image, main={
                'crop': {'x': 0, 'y': 0, 'width': 1200, 'height': 960},
                'width': 600, 'height': 480, 'changed': True})))
        main = first['thumbs']['main']

        second = self.post_crop(self.crop_body(image, main={
            'id': main['id'],
            'crop': main['crop'],
            'width': main['width'],
            'height': main['height'],
            'changed': False,
            'tmp': True,
        }))

        self.assertPayload(second)

    def test_an_orphan_crop_cannot_be_reused_from_another_session(self):
        image = self.uploaded()
        first = self.assertPayload(self.post_crop(self.crop_body(
            image, main={
                'crop': {'x': 0, 'y': 0, 'width': 1200, 'height': 960},
                'width': 600, 'height': 480, 'changed': True})))
        main = first['thumbs']['main']

        other_client = Client()
        other_client.force_login(self.user)
        reopened = self.assertPayload(self.get_state(
            client=other_client,
            image=image['name'], thumbs=str(main['id']),
            sizes=stdlib_json.dumps(serialize(Article.LEAD_IMAGE_SIZES))))

        self.assertNotIn('main', reopened['thumbs'])
        self.assertError(self.post_crop(
            self.crop_body(image, main={
                'id': main['id'], 'crop': main['crop'],
                'width': main['width'], 'height': main['height'],
                'changed': False}),
            client=other_client),
            400, 'invalid', field='thumbs.main')

    @override_settings(CROPDUSTER_CREATE_THUMBS=False)
    def test_metadata_only_orphans_reopen_and_are_reused(self):
        """Reopen orphan geometry when no rendition file was written."""
        image = self.uploaded()
        first = self.assertPayload(self.post_crop(self.crop_body(
            image,
            main={
                'crop': {'x': 15, 'y': 0, 'width': 1270, 'height': 1016},
                'width': 600, 'height': 480, 'changed': True,
            },
            no_height={
                'crop': {'x': 0, 'y': 0, 'width': 1300, 'height': 1016},
                'width': 600, 'height': None, 'changed': True,
            })))

        self.assertEqual(
            sorted(first['thumbs']), ['main', 'no_height', 'thumb'])
        thumb_ids = {
            name: entry['id'] for name, entry in first['thumbs'].items()}
        self.assertTrue(all(thumb_ids.values()))
        self.assertEqual(
            set(Thumb.objects.filter(pk__in=thumb_ids.values()).values_list(
                'image_id', flat=True)),
            {None})

        orphan_image = Image(
            image=image['name'], width=image['width'], height=image['height'])
        tmp_paths = [
            orphan_image.get_image_path(name, tmp=True)
            for name in first['thumbs']]
        for path in tmp_paths:
            self.assertFalse(orphan_image.storage.exists(path), path)

        reopened = self.assertPayload(self.get_state(
            image=image['name'],
            thumbs=','.join(str(pk) for pk in thumb_ids.values()),
            sizes=stdlib_json.dumps(serialize(Article.LEAD_IMAGE_SIZES))))

        self.assertEqual(
            sorted(reopened['thumbs']), ['main', 'no_height', 'thumb'])
        self.assertEqual(
            {name: entry['id'] for name, entry in reopened['thumbs'].items()},
            thumb_ids)
        for name in ('main', 'no_height'):
            self.assertEqual(
                reopened['thumbs'][name]['crop'], first['thumbs'][name]['crop'])

        def unchanged(name):
            entry = reopened['thumbs'][name]
            return {
                'id': entry['id'],
                'crop': entry['crop'],
                'width': entry['width'],
                'height': entry['height'],
                'changed': False,
                'tmp': entry['tmp'],
            }

        row_count = Thumb.objects.count()
        second = self.assertPayload(self.post_crop(self.crop_body(
            reopened['image'],
            main=unchanged('main'),
            no_height=unchanged('no_height'))))

        self.assertEqual(Thumb.objects.count(), row_count)
        for name in ('main', 'no_height'):
            self.assertEqual(second['thumbs'][name]['id'], thumb_ids[name])
            self.assertEqual(
                second['thumbs'][name]['crop'], first['thumbs'][name]['crop'])
        for path in tmp_paths:
            self.assertFalse(orphan_image.storage.exists(path), path)

    def test_a_null_source_is_the_image_being_cropped(self):
        image = self.uploaded()

        self.assertPayload(self.post_crop(self.crop_body(image, main={
            'crop': {'x': 0, 'y': 0, 'width': 1200, 'height': 960},
            'width': 600, 'height': 480, 'changed': True, 'source': None})))

    def test_naming_the_image_itself_as_the_source_is_the_same_thing(self):
        image = self.uploaded()

        self.assertPayload(self.post_crop(self.crop_body(image, main={
            'crop': {'x': 0, 'y': 0, 'width': 1200, 'height': 960},
            'width': 600, 'height': 480, 'changed': True,
            'source': image['name']})))

    def test_any_other_source_is_reserved_wire(self):
        image = self.uploaded()

        response = self.post_crop(self.crop_body(image, main={
            'crop': {'x': 0, 'y': 0, 'width': 1200, 'height': 960},
            'width': 600, 'height': 480, 'changed': True,
            'source': 'somewhere/else.jpg'}))

        error = self.assertError(
            response, 501, 'per_size_source_unsupported', field='thumbs.main')
        self.assertEqual(error['details'], {'source': 'somewhere/else.jpg'})

    def test_a_crop_for_a_size_that_was_not_declared(self):
        image = self.uploaded()

        self.assertError(
            self.post_crop(self.crop_body(image, nope={'changed': False})),
            400, 'unknown_size', field='thumbs')

    def test_an_unknown_image_id(self):
        self.assertError(
            self.post_crop({'image': {'id': 123456}, 'sizes': [], 'thumbs': {}}),
            404, 'not_found')

    def test_an_image_named_neither_way(self):
        self.assertError(
            self.post_crop({'image': {}, 'sizes': [], 'thumbs': {}}),
            400, 'invalid', field='image')

    def test_a_body_that_is_not_json(self):
        response = self.client.post(
            self.crop_url, 'not json', content_type='application/json')

        self.assertError(response, 400, 'invalid', field='body')

    def test_a_crop_box_missing_a_dimension(self):
        image = self.uploaded()

        self.assertError(
            self.post_crop(self.crop_body(image, main={
                'crop': {'x': 0, 'y': 0, 'width': 100}, 'changed': True})),
            400, 'invalid', field='thumbs.main.crop')

    def test_a_crop_box_needs_positive_dimensions(self):
        image = self.uploaded()

        for crop in (
                {'x': -1, 'y': 0, 'width': 100, 'height': 80},
                {'x': 0, 'y': 0, 'width': 0, 'height': 80},
                {'x': 0, 'y': 0, 'width': 100, 'height': -1}):
            with self.subTest(crop=crop):
                self.assertError(
                    self.post_crop(self.crop_body(
                        image, main={'crop': crop, 'changed': True})),
                    400, 'invalid', field='thumbs.main.crop')

    def test_a_crop_box_must_stay_inside_the_image(self):
        image = self.uploaded()

        self.assertError(
            self.post_crop(self.crop_body(image, main={
                'crop': {
                    'x': image['width'] - 10,
                    'y': 0,
                    'width': 20,
                    'height': 10,
                },
                'changed': True,
            })),
            400, 'invalid', field='thumbs.main.crop')

    def test_a_changed_crop_requires_a_crop_box(self):
        image = self.uploaded()

        self.assertError(
            self.post_crop(self.crop_body(
                image, main={'crop': None, 'changed': True})),
            400, 'invalid', field='thumbs.main.crop')

    def test_a_crop_id_must_belong_to_the_image(self):
        _article, image = self.article_image()
        _other_article, other_image = self.article_image()
        other = other_image.thumbs.get(name='main')

        self.assertError(self.post_crop({
            'image': {'id': image.pk},
            'sizes': serialize(Article.LEAD_IMAGE_SIZES),
            'thumbs': {'main': {'id': other.pk, 'changed': False}},
        }), 400, 'invalid', field='thumbs.main')

    def test_a_crop_id_must_name_the_requested_size(self):
        _article, image = self.article_image()
        other_size = image.thumbs.get(name='no_height')

        self.assertError(self.post_crop({
            'image': {'id': image.pk},
            'sizes': serialize(Article.LEAD_IMAGE_SIZES),
            'thumbs': {'main': {'id': other_size.pk, 'changed': False}},
        }), 400, 'invalid', field='thumbs.main')

    def test_file_backed_orphan_needs_its_temporary_rendition(self):
        image = self.uploaded()
        orphan = Thumb.objects.create(
            name='main', width=600, height=480,
            crop_x=15, crop_y=0, crop_w=1270, crop_h=1016)
        image_obj = Image(
            image=image['name'], width=image['width'], height=image['height'])
        self.assertFalse(image_obj.storage.exists(
            image_obj.get_image_path('main', tmp=True)))

        self.assertError(self.post_crop(self.crop_body(
            image, main={'id': orphan.pk, 'changed': False})),
            400, 'invalid', field='thumbs.main')

    @override_settings(CROPDUSTER_CREATE_THUMBS=False)
    def test_metadata_only_orphan_does_not_belong_to_a_saved_image(self):
        _article, image = self.article_image()
        orphan = Thumb.objects.create(
            name='main', width=600, height=480,
            crop_x=15, crop_y=0, crop_w=1270, crop_h=1016)

        self.assertError(self.post_crop({
            'image': {'id': image.pk},
            'sizes': serialize(Article.LEAD_IMAGE_SIZES),
            'thumbs': {'main': {'id': orphan.pk, 'changed': False}},
        }), 400, 'invalid', field='thumbs.main')

    def test_a_standalone_crop_is_named_after_its_contents(self):
        image = self.assertPayload(self.post_upload(
            standalone='true',
            sizes=stdlib_json.dumps(serialize([Size('crop')]))))['image']

        payload = self.assertPayload(self.post_crop({
            'image': {'id': image['id']},
            'standalone': True,
            'sizes': serialize([Size('crop')]),
            'thumbs': {
                'crop': {
                    'crop': {'x': 0, 'y': 0, 'width': 1200, 'height': 900},
                    'width': 1200, 'height': 900,
                    'changed': True,
                },
            },
        }))

        self.assertEqual(len(payload['thumbs']), 1)
        self.assertNotIn('crop', payload['thumbs'])

    def test_standalone_without_the_extra_is_refused_actionably(self):
        image = self.uploaded()

        with mock.patch('cropduster.standalone.standalone_available',
                        return_value=False):
            response = self.post_crop(dict(
                self.crop_body(image), standalone=True))

        error = self.assertError(
            response, 501, 'standalone_unavailable', field='standalone')
        self.assertIn(NOT_INSTALLED_MESSAGE, error['message'])

    def test_a_body_over_the_upload_limit(self):
        with override_settings(DATA_UPLOAD_MAX_MEMORY_SIZE=10):
            response = self.post_crop({'image': {'name': 'x' * 100}})

        self.assertError(response, 413, 'request_too_large')

    def test_a_crop_too_small_for_the_size_it_is_drawn_for(self):
        image = self.uploaded(sizes=[SMALL])

        response = self.post_crop(self.crop_body(
            image, sizes=[SMALL],
            small={'crop': {'x': 0, 'y': 0, 'width': 10, 'height': 8},
                   'width': 100, 'height': 80, 'changed': True}))

        self.assertError(response, 400, 'resize_failed')


class TestTarget(ApiTestCase):
    """Use the target model field as the source of upload configuration.

    A client may select a subset of the field's sizes, but it cannot replace
    their geometry, lower their minimum dimensions, or change the field's
    upload directory.
    """

    def target(self, article=None, field_name='lead_image'):
        return {
            'content_type': 'tests.article',
            'object_id': article.pk if article else None,
            'field_name': field_name,
        }

    def test_the_sizes_come_from_the_field(self):
        payload = self.assertPayload(self.post_upload(
            target=stdlib_json.dumps(self.target())))

        self.assertEqual(
            [size['name'] for size in payload['sizes']], ['main', 'no_height'])

    def test_the_upload_directory_comes_from_the_field(self):
        payload = self.assertPayload(self.post_upload(
            upload_to='anywhere/i/like',
            target=stdlib_json.dumps(self.target())))

        self.assertTrue(payload['image']['name'].startswith('article/lead_image/'))

    def test_a_client_may_narrow_the_sizes_by_name(self):
        payload = self.assertPayload(self.post_upload(
            sizes=stdlib_json.dumps(serialize([Article.LEAD_IMAGE_SIZES[1]])),
            target=stdlib_json.dumps(self.target())))

        self.assertEqual([size['name'] for size in payload['sizes']], ['no_height'])

    def test_a_client_may_not_invent_sizes(self):
        response = self.post_upload(
            sizes=stdlib_json.dumps(serialize([SMALL])),
            target=stdlib_json.dumps(self.target()))

        error = self.assertError(response, 400, 'sizes_not_allowed', field='sizes')
        self.assertEqual(error['details']['refused'], ['small'])
        self.assertEqual(error['details']['allowed'], ['main', 'no_height'])

    def test_the_declared_minimum_is_what_an_upload_has_to_clear(self):
        """Resolve size names to the field's declared Size objects.

        ``OrphanedThumbs.main`` has a 1200x960 auto size, so the upload must
        meet that minimum even when the request defines ``main`` as 1x1.
        """
        harmless = Size('main', w=1, h=1)

        response = self.post_upload(
            'img.jpg', sizes=stdlib_json.dumps(serialize([harmless])),
            target=stdlib_json.dumps({
                'content_type': 'tests.orphanedthumbs', 'field_name': 'image'}))

        error = self.assertError(response, 400, 'image_too_small')
        self.assertEqual(error['details']['min'], [1200, 960])

    def test_a_model_that_does_not_exist(self):
        self.assertError(
            self.get_state(target=stdlib_json.dumps(
                {'content_type': 'tests.nope', 'field_name': 'lead_image'})),
            400, 'unknown_model', field='target')

    def test_a_field_that_is_not_a_cropduster_field(self):
        self.assertError(
            self.get_state(target=stdlib_json.dumps(
                {'content_type': 'tests.article', 'field_name': 'title'})),
            400, 'unknown_field', field='target')

    def test_a_target_missing_its_field_name(self):
        self.assertError(
            self.get_state(target=stdlib_json.dumps({'content_type': 'tests.article'})),
            400, 'invalid', field='target')

    def test_state_hydrates_a_saved_object_from_its_field(self):
        article, image = self.article_image()

        payload = self.assertPayload(self.get_state(
            id=image.pk, target=stdlib_json.dumps(self.target(article))))

        self.assertEqual(
            [size['name'] for size in payload['sizes']], ['main', 'no_height'])
        self.assertEqual(payload['image']['id'], image.pk)

    def test_target_and_image_must_name_the_same_field(self):
        article, _image = self.article_image()
        _other_article, other_image = self.article_image()

        self.assertError(self.get_state(
            id=other_image.pk,
            target=stdlib_json.dumps(self.target(article))),
            400, 'target_mismatch', field='image')

    def test_a_crop_may_not_invent_a_size_either(self):
        """Reject crop sizes not declared by the target field.

        The crop request includes the widget's target in its JSON body. The
        target field remains authoritative regardless of the accompanying size
        definitions.
        """
        image = self.uploaded(sizes=Article.LEAD_IMAGE_SIZES)

        response = self.post_crop(dict(
            self.crop_body(
                image, sizes=[SMALL],
                small={'crop': {'x': 0, 'y': 0, 'width': 100, 'height': 80},
                       'width': 100, 'height': 80, 'changed': True}),
            target=self.target()))

        error = self.assertError(response, 400, 'sizes_not_allowed', field='sizes')
        self.assertEqual(error['details']['refused'], ['small'])

    def test_a_crop_names_an_unsaved_object_with_a_null_id(self):
        """An add-form target has no object id but still uses field sizes."""
        image = self.uploaded(sizes=Article.LEAD_IMAGE_SIZES)

        payload = self.assertPayload(self.post_crop(dict(
            self.crop_body(image, main={
                'crop': {'x': 0, 'y': 0, 'width': 1200, 'height': 960},
                'width': 600, 'height': 480, 'changed': True}),
            sizes=None,
            target={'content_type': 'tests.article', 'object_id': None,
                    'field_name': 'lead_image'})))

        self.assertEqual(
            [size['name'] for size in payload['sizes']], ['main', 'no_height'])

    def test_crop_takes_its_sizes_from_the_field_too(self):
        image = self.uploaded(sizes=Article.LEAD_IMAGE_SIZES)

        payload = self.assertPayload(self.post_crop(dict(
            self.crop_body(image, main={
                'crop': {'x': 0, 'y': 0, 'width': 1200, 'height': 960},
                'width': 600, 'height': 480, 'changed': True}),
            sizes=None, target=self.target())))

        self.assertEqual(
            [size['name'] for size in payload['sizes']], ['main', 'no_height'])
        self.assertEqual(payload['thumbs']['main']['width'], 600)


class TestCallableSizes(ApiTestCase):
    """Pass the target object and its current image to callable sizes.

    Both arguments are ``None`` when the target object has not been saved.
    """

    def use_callable_sizes(self):
        field = Article._meta.get_field('lead_image')
        declared = field.sizes
        seen = []

        def sizes(instance, related=None):
            seen.append((instance, related))
            return declared

        field.sizes = sizes
        self.addCleanup(setattr, field, 'sizes', declared)
        return seen

    def test_it_is_called_with_the_object_being_edited(self):
        article, image = self.article_image()
        seen = self.use_callable_sizes()

        self.assertPayload(self.get_state(id=image.pk, target=stdlib_json.dumps({
            'content_type': 'tests.article',
            'object_id': article.pk,
            'field_name': 'lead_image',
        })))

        self.assertEqual(seen, [(article, image)])

    def test_it_is_called_with_nothing_when_there_is_no_object_yet(self):
        seen = self.use_callable_sizes()

        self.assertPayload(self.get_state(target=stdlib_json.dumps({
            'content_type': 'tests.article',
            'field_name': 'lead_image',
        })))

        self.assertEqual(seen, [(None, None)])


class TestCsrf(ApiTestCase):

    def csrf_client(self, user=None):
        """Return a CSRF-enforcing client and a token valid for its cookie."""
        client = Client(enforce_csrf_checks=True)
        client.force_login(user or self.user)

        request = test.RequestFactory().get('/')
        token = get_token(request)
        client.cookies[django_settings.CSRF_COOKIE_NAME] = request.META['CSRF_COOKIE']
        return client, token

    def test_upload_without_a_token(self):
        client, token = self.csrf_client()

        self.assertError(
            self.post_upload(client=client), 403, 'csrf_failed')

    def test_upload_with_a_token(self):
        client, token = self.csrf_client()
        client.defaults['HTTP_X_CSRFTOKEN'] = token

        self.assertPayload(self.post_upload(client=client))

    def test_crop_without_a_token(self):
        client, token = self.csrf_client()

        self.assertError(
            self.post_crop({'image': {}}, client=client), 403, 'csrf_failed')

    def test_crop_with_a_token(self):
        client, token = self.csrf_client()
        client.defaults['HTTP_X_CSRFTOKEN'] = token
        image = self.uploaded()

        self.assertPayload(self.post_crop(self.crop_body(image), client=client))

    def test_state_without_a_token(self):
        client, _token = self.csrf_client()

        self.assertError(
            self.get_state(client=client), 403, 'csrf_failed')

    def test_state_with_a_token(self):
        client, token = self.csrf_client()
        client.defaults['HTTP_X_CSRFTOKEN'] = token

        self.assertPayload(self.get_state(client=client))

    @override_settings(CROPDUSTER_API_PERMISSION='tests.test_api.refuse_everyone')
    def test_csrf_is_checked_before_permission(self):
        client, _token = self.csrf_client()

        self.assertError(
            self.post_upload(client=client), 403, 'csrf_failed')

    def test_method_is_checked_before_csrf_for_put(self):
        client, _token = self.csrf_client()
        response = client.put(
            self.upload_url, '{}', content_type='application/json')

        self.assertError(response, 405, 'method_not_allowed')


class TestLegacyCsrfExemption(ApiTestCase):
    """Keep legacy POST endpoints CSRF-exempt during the 5.x series.

    Existing clients do not send CSRF tokens. Setting
    ``CROPDUSTER_LEGACY_CSRF_EXEMPT`` to false enables the protection that
    becomes the default in 6.0.
    """

    def post_legacy_upload(self, client):
        with open(os.path.join(self.TEST_IMG_DIR, 'img2.jpg'), 'rb') as f:
            return client.post(reverse('cropduster-upload'), {
                'image': f, 'upload_to': 'test', 'sizes': '[]'})

    def enforcing_client(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        return client

    def test_exempt_by_default(self):
        response = self.post_legacy_upload(self.enforcing_client())

        self.assertEqual(response.status_code, 200)
        self.assertNotIn('error', stdlib_json.loads(response.content))

    @override_settings(CROPDUSTER_LEGACY_CSRF_EXEMPT=False)
    def test_protected_when_the_exemption_is_turned_off(self):
        response = self.post_legacy_upload(self.enforcing_client())

        self.assertEqual(response.status_code, 403)

    @override_settings(CROPDUSTER_LEGACY_CSRF_EXEMPT=False)
    def test_a_token_is_accepted_when_the_exemption_is_turned_off(self):
        client = self.enforcing_client()
        request = test.RequestFactory().get('/')
        client.defaults['HTTP_X_CSRFTOKEN'] = get_token(request)
        client.cookies[django_settings.CSRF_COOKIE_NAME] = request.META['CSRF_COOKIE']

        response = self.post_legacy_upload(client)

        self.assertEqual(response.status_code, 200)

    def test_the_setting_is_read_per_request(self):
        """Read the exemption setting at request time, not at import time."""
        from django.urls import resolve

        view = resolve(reverse('cropduster-upload')).func

        self.assertIs(view.csrf_exempt, True)
        with override_settings(CROPDUSTER_LEGACY_CSRF_EXEMPT=False):
            self.assertIs(view.csrf_exempt, False)


class TestPermissions(ApiTestCase):

    def client_for(self, user=None):
        client = Client()
        if user is not None:
            client.force_login(user)
        return client

    def staff(self, **perms):
        user = User.objects.create_user(
            'staff-%d' % User.objects.count(), 'staff@test.com', 'password',
            is_staff=True)
        for codename in perms.pop('permissions', ()):
            user.user_permissions.add(Permission.objects.get(
                codename=codename, content_type__app_label='tests'))
        return user

    def target(self, article=None):
        return stdlib_json.dumps({
            'content_type': 'tests.article',
            'object_id': article.pk if article else None,
            'field_name': 'lead_image',
        })

    def test_anonymous_is_refused_rather_than_redirected(self):
        response = self.get_state(client=self.client_for())

        self.assertError(response, 403, 'permission_denied')

    def test_a_user_who_is_not_staff_is_refused(self):
        user = User.objects.create_user('reader', 'reader@test.com', 'password')

        self.assertError(
            self.get_state(client=self.client_for(user)), 403, 'permission_denied')

    def test_an_inactive_staff_member_is_refused(self):
        user = self.staff()
        user.is_active = False
        user.save()

        self.assertError(
            self.get_state(client=self.client_for(user)), 403, 'permission_denied')

    def test_staff_may_work_on_an_image_that_is_attached_to_nothing(self):
        self.assertPayload(self.get_state(client=self.client_for(self.staff())))

    def test_saved_image_id_infers_the_target_permission(self):
        _article, image = self.article_image()

        self.assertError(
            self.get_state(
                client=self.client_for(self.staff()), id=image.pk),
            403, 'permission_denied')

        user = self.staff(permissions=['change_article'])
        self.assertPayload(
            self.get_state(client=self.client_for(user), id=image.pk))

    def test_saved_image_name_infers_the_target_permission(self):
        _article, image = self.article_image()

        with mock.patch('cropduster.api.views.ImageFile') as image_file:
            self.assertError(
                self.get_state(
                    client=self.client_for(self.staff()), image=image.name),
                403, 'permission_denied')

        image_file.assert_not_called()

    def test_replacement_filename_does_not_skip_the_saved_images_permission(self):
        _article, image = self.article_image()
        replacement = self.create_unique_image('img.jpg')

        self.assertError(
            self.get_state(
                client=self.client_for(self.staff()),
                id=image.pk, image=replacement),
            403, 'permission_denied')

    def test_saved_crop_without_target_infers_the_target_permission(self):
        _article, image = self.article_image()

        self.assertError(self.post_crop({
            'image': {'id': image.pk},
            'sizes': [],
            'thumbs': {},
        }, client=self.client_for(self.staff())), 403, 'permission_denied')

    def test_staff_without_the_model_permission_may_not_name_it_as_a_target(self):
        article, image = self.article_image()

        self.assertError(
            self.get_state(client=self.client_for(self.staff()),
                           target=self.target(article)),
            403, 'permission_denied')

    def test_the_change_permission_is_what_editing_a_saved_object_needs(self):
        article, image = self.article_image()
        user = self.staff(permissions=['change_article'])

        self.assertPayload(
            self.get_state(client=self.client_for(user), target=self.target(article)))

    def test_the_add_permission_is_what_an_unsaved_object_needs(self):
        user = self.staff(permissions=['add_article'])

        self.assertPayload(
            self.get_state(client=self.client_for(user), target=self.target()))

        # The change permission does not satisfy the add permission check.
        other = User.objects.create_user(
            'other', 'other@test.com', 'password', is_staff=True)
        other.user_permissions.add(Permission.objects.get(
            codename='change_article', content_type__app_label='tests'))
        self.assertError(
            self.get_state(client=self.client_for(other), target=self.target()),
            403, 'permission_denied')

    @override_settings(
        CROPDUSTER_API_PERMISSION='cropduster.api.permissions.login_required_only')
    def test_login_required_only_lets_any_logged_in_user_in(self):
        user = User.objects.create_user('reader', 'reader@test.com', 'password')

        self.assertPayload(self.get_state(client=self.client_for(user)))
        self.assertError(
            self.get_state(client=self.client_for()), 403, 'permission_denied')

    @override_settings(CROPDUSTER_API_PERMISSION='tests.test_api.refuse_everyone')
    def test_a_custom_callable_is_honoured(self):
        error = self.assertError(self.get_state(), 403, 'permission_denied')

        self.assertEqual(error['message'], "Not today.")

    @override_settings(CROPDUSTER_API_PERMISSION='tests.test_api.allow_anyone')
    def test_a_custom_callable_may_let_anonymous_users_in(self):
        self.assertPayload(self.get_state(client=self.client_for()))

    @override_settings(CROPDUSTER_API_PERMISSION='tests.test_api.return_false')
    def test_a_false_return_value_refuses_the_request(self):
        self.assertError(self.get_state(), 403, 'permission_denied')

    @override_settings(CROPDUSTER_API_PERMISSION='tests.test_api.refuse_everyone')
    def test_every_endpoint_is_guarded(self):
        self.assertError(self.get_state(), 403, 'permission_denied')
        self.assertError(self.post_upload(), 403, 'permission_denied')
        self.assertError(self.post_crop({'image': {}}), 403, 'permission_denied')

    def test_the_permission_check_runs_before_the_request_is_read(self):
        """Permission denial takes precedence over request validation."""
        self.assertError(
            self.get_state(client=self.client_for(),
                           target=stdlib_json.dumps({
                               'content_type': 'tests.nope',
                               'field_name': 'lead_image'})),
            403, 'permission_denied')


class TestApiSettings(test.SimpleTestCase):

    def test_defaults(self):
        self.assertEqual(
            cropduster_settings.CROPDUSTER_API_PERMISSION,
            'cropduster.api.permissions.staff_and_object_perm')
        self.assertIs(cropduster_settings.CROPDUSTER_LEGACY_CSRF_EXEMPT, True)
        self.assertIs(cropduster_settings.CROPDUSTER_REMOTE_IMAGE_FETCH, True)

    def test_they_are_named_in_setting_names(self):
        self.assertIn('CROPDUSTER_API_PERMISSION', cropduster_conf.SETTING_NAMES)
        self.assertIn('CROPDUSTER_LEGACY_CSRF_EXEMPT', cropduster_conf.SETTING_NAMES)
        self.assertIn('CROPDUSTER_REMOTE_IMAGE_FETCH', cropduster_conf.SETTING_NAMES)

    def test_no_deprecation_warning_is_raised_for_the_legacy_exemption(self):
        """Document the 6.0 default change without emitting a warning.

        Since the 5.x default is true, a warning would affect every project,
        including projects whose clients cannot yet send CSRF tokens.
        """
        with warnings.catch_warnings(record=True) as raised:
            warnings.simplefilter("always")
            cropduster_settings.CROPDUSTER_LEGACY_CSRF_EXEMPT

        self.assertEqual(raised, [])


class TestErrorEnvelope(ApiTestCase):

    def test_a_method_the_endpoint_does_not_accept(self):
        self.assertError(
            self.client.get(self.upload_url), 405, 'method_not_allowed')

    def test_an_unexpected_error_is_logged_and_answered_as_a_bare_500(self):
        with mock.patch('cropduster.api.views.build_payload',
                        side_effect=RuntimeError("boom")):
            with self.assertLogs('cropduster', level='ERROR') as logged:
                response = self.get_state()

        error = self.assertError(response, 500, 'server_error')
        self.assertNotIn('boom', error['message'])
        self.assertIn('boom', '\n'.join(logged.output))

    def test_the_endpoints_are_not_cached(self):
        response = self.get_state()

        self.assertIn('no-store', response['Cache-Control'])

    def test_the_endpoints_may_be_framed(self):
        """Allow an editor to embed the crop dialog in an iframe."""
        response = self.get_state()

        self.assertTrue(getattr(response, 'xframe_options_exempt', False))
