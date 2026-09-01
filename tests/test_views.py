import os

from django import test
from django.core.files.storage import FileSystemStorage, default_storage
try:
    from django.urls import reverse
except ImportError:
    from django.core.urlresolvers import reverse
from django.contrib.auth.models import User
from django.http import HttpRequest

from cropduster import views
from cropduster.utils import json

from .helpers import CropdusterTestCaseMediaMixin


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
            views.upload(request).content,
            views.index(request).content)

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
