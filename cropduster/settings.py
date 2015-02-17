import math
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

CROPDUSTER_PREVIEW_WIDTH = getattr(settings, 'CROPDUSTER_PREVIEW_WIDTH', 800)
CROPDUSTER_PREVIEW_HEIGHT = getattr(settings, 'CROPDUSTER_PREVIEW_HEIGHT', 500)


def get_jpeg_quality(width, height):
    p = math.sqrt(width * height)
    if p >= 1750:
        return 80
    elif p >= 1000:
        return 85
    else:
        return 90

get_jpeg_quality = getattr(settings, 'get_jpeg_quality', get_jpeg_quality)
