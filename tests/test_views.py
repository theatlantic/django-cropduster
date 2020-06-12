import os

from django import test
from django.core.files.storage import default_storage
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
        img_file = open(os.path.join(self.TEST_IMG_DIR, 'img.jpg'), 'rb')
        data = {
            u'image': img_file,
            u'upload_to': [u'test'],
            u'image_element_id': u'mt_image',
            u'md5': u'',
            u'preview_height': u'500',
            u'preview_width': u'800',
            u'sizes': u'''
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
