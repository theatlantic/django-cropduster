import os
import django
import uuid

from selenosis.settings import *


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
    'cropduster.tests',
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
