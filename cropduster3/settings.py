import os.path

from django.conf import settings


CROPDUSTER_ROOT = os.path.normpath(os.path.dirname(__file__))
CROPDUSTER_MEDIA_ROOT = os.path.join(CROPDUSTER_ROOT, 'media')

MAX_WIDTH = 1000
MAX_HEIGHT = 1000

try:
    CROPDUSTER_APP_LABEL = getattr(settings, 'CROPDUSTER_V3_APP_LABEL')
except AttributeError:
    CROPDUSTER_APP_LABEL = getattr(settings, 'CROPDUSTER_APP_LABEL', 'cropduster3')

try:
    CROPDUSTER_DB_PREFIX = getattr(settings, 'CROPDUSTER_V3_DB_PREFIX')
except AttributeError:
    CROPDUSTER_DB_PREFIX = getattr(settings, 'CROPDUSTER_DB_PREFIX', 'cropduster')
