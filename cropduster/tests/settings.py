import os
import uuid

import django
from django.core.signals import setting_changed
from django.dispatch import receiver
from django.utils.functional import lazy
from django.urls import reverse

from selenosis.settings import *


lazy_reverse = lazy(reverse, str)


if django.VERSION > (1, 11):
    MIGRATION_MODULES = {
        'auth': None,
        'contenttypes': None,
        'sessions': None,
        'cropduster': None,
    }

INSTALLED_APPS += (
    'generic_plus',
    'cropduster',
    'cropduster.standalone',
    'cropduster.tests',
    'cropduster.tests.test_standalone',
    'ckeditor',
)

ROOT_URLCONF = 'cropduster.tests.urls'

TEMPLATES[0]['OPTIONS']['debug'] = True

if os.environ.get('S3') == '1':
    DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
    AWS_STORAGE_BUCKET_NAME = 'ollie-cropduster-media-test-bucket-dev'
    AWS_DEFAULT_ACL = 'public-read'
    AWS_LOCATION = 'cropduster/%s/' % uuid.uuid4().hex
    AWS_S3_SIGNATURE_VERSION = 's3v4'
else:
    DEFAULT_FILE_STORAGE = 'django.core.files.storage.FileSystemStorage'

CKEDITOR_CONFIGS = {
    'default': {
        'extraPlugins': 'cropduster',
        'removePlugins': 'flash,forms,contextmenu,liststyle,table,tabletools,iframe',
        'disableAutoInline': True,
        "height": 450,
        "width": 840,
        'cropduster_uploadTo': 'ckeditor',
        'cropduster_previewSize': [570, 300],
        'cropduster_url': lazy_reverse('cropduster-standalone'),
        'cropduster_urlParams': {'max_w': 672, 'full_w': 960},
    },
}

CKEDITOR_UPLOAD_PATH = "%s/upload" % MEDIA_ROOT
CROPDUSTER_CREATE_THUMBS = True


@receiver(setting_changed)
def reload_settings(**kwargs):
    if kwargs['setting'] == 'CROPDUSTER_CREATE_THUMBS':
        from cropduster import settings as cropduster_settings
        cropduster_settings.CROPDUSTER_CREATE_THUMBS = kwargs['value']

os.makedirs(CKEDITOR_UPLOAD_PATH)
