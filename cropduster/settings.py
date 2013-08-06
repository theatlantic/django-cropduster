import os
from django.conf import settings


CROPDUSTER_MEDIA_ROOT = getattr(settings, 'CROPDUSTER_MEDIA_ROOT', settings.MEDIA_ROOT)

try:
    CROPDUSTER_APP_LABEL = getattr(settings, 'CROPDUSTER_V4_APP_LABEL')
except AttributeError:
    CROPDUSTER_APP_LABEL = getattr(settings, 'CROPDUSTER_APP_LABEL', 'cropduster')

try:
    CROPDUSTER_DB_PREFIX = getattr(settings, 'CROPDUSTER_V4_DB_PREFIX')
except AttributeError:
    CROPDUSTER_DB_PREFIX = getattr(settings, 'CROPDUSTER_DB_PREFIX', 'cropduster4')

CROPDUSTER_UPLOAD_PATH = getattr(settings, 'CROPDUSTER_UPLOAD_PATH', settings.MEDIA_ROOT)

if not CROPDUSTER_UPLOAD_PATH.startswith('/'): # Sorry Windows people
    CROPDUSTER_UPLOAD_PATH = os.path.join(settings.MEDIA_ROOT, CROPDUSTER_UPLOAD_PATH)
