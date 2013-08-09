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
