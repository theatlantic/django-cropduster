import os
import re

from django import test
from django.core.files.storage import FileSystemStorage, default_storage
try:
    from django.urls import reverse
except ImportError:
    from django.core.urlresolvers import reverse
from django.contrib.auth.models import User
from django.http import HttpRequest

from cropduster import views
from cropduster.models import Image, Thumb
from cropduster.utils import json

from .helpers import CropdusterTestCaseMediaMixin
from .models import Author


#: The dialog config's CSRF token, which is masked afresh on every call to
#: ``get_token()`` and so differs between two renders of the same page.
CSRF_TOKEN_RE = re.compile(br'(&quot;csrfToken&quot;:\s*&quot;)[^&]*')


def without_csrf_token(content):
    return CSRF_TOKEN_RE.sub(br'\1', content)


class CropdusterViewTestRunner(CropdusterTestCaseMediaMixin, test.TestCase):
    def setUp(self):
        super(CropdusterViewTestRunner, self).setUp()
        self.factory = test.RequestFactory()
        self.user = User.objects.create_superuser('test',
            'test@test.com', 'password')


class TestIndex(CropdusterViewTestRunner):

    def test_get_is_200(self):
        request = self.factory.get(reverse('cropduster-index'))
        request.user = self.user
        response = views.index(request)
        self.assertEqual(response.status_code, 200)

    def test_get_with_protocol_relative_image_param_is_200(self):
        # urlopen() raises ValueError for protocol-relative URLs, so
        # ImageFile must treat them as invalid rather than fetch them
        request = self.factory.get(
            reverse('cropduster-index'), {'image': '//example.com/photo.jpg'})
        request.user = self.user
        response = views.index(request)
        self.assertEqual(response.status_code, 200)

    def test_post_is_405(self):
        request = self.factory.post(reverse('cropduster-index'), {})
        request.user = self.user
        response = views.index(request)
        self.assertEqual(response.status_code, 405)


class TestUpload(CropdusterViewTestRunner):

    def test_get_request(self):
        request = HttpRequest()
        request.method = "GET"
        request.user = self.user
        self.assertEqual(
            without_csrf_token(views.upload(request).content),
            without_csrf_token(views.index(request).content))

    def test_post_request(self):
        with open(os.path.join(self.TEST_IMG_DIR, 'img.jpg'), 'rb') as img_file:
            data = {
                'image': img_file,
                'upload_to': ['test'],
                'image_element_id': 'mt_image',
                'md5': '',
                'preview_height': '500',
                'preview_width': '800',
                'sizes': '''
                [{
                "auto": [{
                            "max_w": null,
                            "retina": 0,
                            "min_h": 1,
                            "name": "lead",
                            "w": 570,
                            "h": null,
                            "min_w": 570,
                            "__type__": "Size",
                            "max_h": null,
                            "label": "Lead"
                        }, {
                            "max_w": null,
                            "retina": 0,
                            "min_h": 110,
                            "name": "featured_small",
                            "w": 170,
                            "h": 110,
                            "min_w": 170,
                            "__type__": "Size",
                            "max_h": null,
                            "label": "Featured Small"
                        }, {
                            "max_w": null,
                            "retina": 0,
                            "min_h": 250,
                            "name": "featured_large",
                            "w": 386,
                            "h": 250,
                            "min_w": 386,
                            "__type__": "Size",
                            "max_h": null,
                            "label": "Featured Large"
                        }],
                "retina": 0,
                "name": "lead_large",
                "h": null,
                "min_w": 615,
                "__type__": "Size",
                "max_h": null,
                "label": "Lead Large",
                "max_w": null,
                "min_h": 250,
                "w": 615
            }]''',
            }
            request = self.factory.post(reverse('cropduster-upload'), data)
            request.user = self.user
            response = views.upload(request)
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.content)
            self.assertTrue(default_storage.exists(data['orig_image']))

    def _standalone_upload(self, upload_to):
        with open(os.path.join(self.TEST_IMG_DIR, 'img.jpg'), 'rb') as img_file:
            request = self.factory.post(reverse('cropduster-upload'), {
                'image': img_file,
                'upload_to': upload_to,
                'image_element_id': 'mt_image',
                'md5': '',
                'standalone': '1',
                'preview_height': '500',
                'preview_width': '800',
            })
        request.user = self.user
        response = views.upload(request)
        self.assertEqual(response.status_code, 200)
        return json.loads(response.content)

    def test_duplicate_standalone_upload_deletes_duplicate_original(self):
        first = self._standalone_upload('dedup')
        second = self._standalone_upload('dedup')

        # upload() responds with the image retained for this md5
        self.assertEqual(second['orig_image'], first['orig_image'])
        self.assertEqual(second['crop']['orig_image'], first['orig_image'])
        self.assertTrue(default_storage.exists(first['orig_image']))

        # The original written while validating the duplicate upload (and
        # the directory allocated for it) must not be left behind
        duplicate_dir = "%s-1" % os.path.dirname(first['orig_image'])
        self.assertFalse(default_storage.exists("%s/original.jpg" % duplicate_dir))
        if isinstance(default_storage, FileSystemStorage):
            self.assertFalse(os.path.isdir(default_storage.path(duplicate_dir)))


class TestCrop(CropdusterViewTestRunner):

    def _crop_post(self, image, thumb_pk, box, changed):
        data = {
            'crop-image_id': image.pk,
            'crop-orig_image': image.image.name,
            'crop-orig_w': str(image.width),
            'crop-orig_h': str(image.height),
            'crop-sizes': json.dumps(Author.HEADSHOT_SIZES),
            'crop-thumbs': '{}',
            'thumbs-TOTAL_FORMS': '1',
            'thumbs-INITIAL_FORMS': '1',
            'thumbs-MIN_NUM_FORMS': '0',
            'thumbs-MAX_NUM_FORMS': '1000',
            'thumbs-0-id': str(thumb_pk),
            'thumbs-0-name': 'main',
            'thumbs-0-width': '220',
            'thumbs-0-height': '180',
            'thumbs-0-crop_x': str(box[0]),
            'thumbs-0-crop_y': str(box[1]),
            'thumbs-0-crop_w': str(box[2]),
            'thumbs-0-crop_h': str(box[3]),
            'thumbs-0-size': json.dumps(Author.HEADSHOT_SIZES[0]),
            'thumbs-0-thumbs': '{}',
        }
        if changed:
            data['thumbs-0-changed'] = 'on'
        request = self.factory.post(reverse('cropduster-crop'), data)
        request.user = self.user
        response = views.crop(request)
        self.assertEqual(response.status_code, 200)
        return json.loads(response.content)

    def test_reopen_and_unchanged_save_preserves_recrop_rendition(self):
        """
        The crop view must not regenerate the tmp rendition from the saved
        one when the dialog is reopened before the parent form saves and
        then saved without further changes: Thumb.save() copies the tmp
        rendition over the saved one on the parent form's save, so the
        re-cropped Thumb row would keep the new coordinates while the
        saved rendition kept the old pixels.
        """
        author = Author.objects.create(
            name="test", headshot=self.create_unique_image('img.jpg'))
        author.headshot.generate_thumbs()

        image = Image.objects.get(object_id=author.pk)
        main_thumb = image.thumbs.get(name='main')
        new_box = (10, 10, 440, 360)
        self.assertNotEqual(
            new_box,
            (main_thumb.crop_x, main_thumb.crop_y, main_thumb.crop_w, main_thumb.crop_h))

        # Re-crop in the dialog
        crop_data = self._crop_post(image, main_thumb.pk, new_box, changed=True)
        recropped_pk = crop_data['thumbs'][0]['id']
        self.assertNotEqual(recropped_pk, main_thumb.pk)

        tmp_path = image.get_image_path('main', tmp=True)
        final_path = image.get_image_path('main')
        with default_storage.open(tmp_path, 'rb') as f:
            recropped_rendition = f.read()
        with default_storage.open(final_path, 'rb') as f:
            saved_rendition = f.read()
        self.assertNotEqual(recropped_rendition, saved_rendition)

        # Reopen the dialog (the index view reinitializes every thumb form
        # with changed=False) and save without moving the crop box
        self._crop_post(image, recropped_pk, new_box, changed=False)

        with default_storage.open(tmp_path, 'rb') as f:
            self.assertEqual(f.read(), recropped_rendition,
                "The unchanged save overwrote the re-crop's tmp rendition")

        # On the parent form's save, ManyToManyField.save_form_data
        # assigns the selected thumbs and Thumb.save() copies each tmp
        # rendition over its saved one; thumbs.set() is that same
        # assignment
        selected_pks = [t['id'] for t in crop_data['crop']['thumbs'].values()]
        image.thumbs.set(Thumb.objects.filter(pk__in=selected_pks))

        recropped = Thumb.objects.get(pk=recropped_pk)
        self.assertEqual(
            new_box,
            (recropped.crop_x, recropped.crop_y, recropped.crop_w,
             recropped.crop_h))
        with default_storage.open(final_path, 'rb') as f:
            self.assertEqual(f.read(), recropped_rendition,
                "The saved rendition does not match the re-crop")

    def test_unchanged_save_regenerates_missing_tmp_rendition(self):
        """
        When the dialog is opened on a saved crop and saved without
        changes, the crop view copies the saved rendition to the tmp path,
        so that Thumb.save() writes the same pixels back on the parent
        form's save.
        """
        author = Author.objects.create(
            name="test", headshot=self.create_unique_image('img.jpg'))
        author.headshot.generate_thumbs()

        image = Image.objects.get(object_id=author.pk)
        main_thumb = image.thumbs.get(name='main')
        box = (main_thumb.crop_x, main_thumb.crop_y,
               main_thumb.crop_w, main_thumb.crop_h)

        self._crop_post(image, main_thumb.pk, box, changed=False)

        tmp_path = image.get_image_path('main', tmp=True)
        final_path = image.get_image_path('main')
        with default_storage.open(final_path, 'rb') as f:
            saved_rendition = f.read()
        with default_storage.open(tmp_path, 'rb') as f:
            self.assertEqual(f.read(), saved_rendition)
