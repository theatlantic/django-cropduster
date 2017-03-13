import math
import PIL
import distutils.spawn
from distutils.version import LooseVersion
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils import six


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


def default_jpeg_quality(width, height):
    p = math.sqrt(width * height)
    if p >= 1750:
        return 80
    elif p >= 1000:
        return 85
    else:
        return 90

CROPDUSTER_JPEG_QUALITY = getattr(settings, 'CROPDUSTER_JPEG_QUALITY', default_jpeg_quality)


def get_jpeg_quality(width, height):
    if six.callable(CROPDUSTER_JPEG_QUALITY):
        return CROPDUSTER_JPEG_QUALITY(width, height)
    elif isinstance(CROPDUSTER_JPEG_QUALITY, (int, float)):
        return CROPDUSTER_JPEG_QUALITY
    else:
        raise ImproperlyConfigured(
            "CROPDUSTER_JPEG_QUALITY setting must be either a callable "
            "or a numeric value, got type %s" % (type(CROPDUSTER_JPEG_QUALITY).__name__))

JPEG_SAVE_ICC_SUPPORTED = (LooseVersion(getattr(PIL, 'PILLOW_VERSION', '0'))
    >= LooseVersion('2.2.1'))

CROPDUSTER_GIFSICLE_PATH = getattr(settings, 'CROPDUSTER_GIFSICLE_PATH', None)

if CROPDUSTER_GIFSICLE_PATH is None:
    # Try to find executable in the PATH
    CROPDUSTER_GIFSICLE_PATH = distutils.spawn.find_executable("gifsicle")

CROPDUSTER_RETAIN_METADATA = getattr(settings, 'CROPDUSTER_RETAIN_METADATA', False)
