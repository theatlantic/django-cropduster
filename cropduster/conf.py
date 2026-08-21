"""Read Cropduster settings from ``django.conf.settings`` when accessed.

The app label and database prefix are exceptions because Django uses them
while building model metadata; they are read once at import, and a later
change has no effect on the registered models. Existing migrations use
the ``"cropduster"`` app label, so ``cropduster.E010`` reports an override
before migration loading fails.
"""

import math
import shutil

from django.conf import settings as django_settings
from django.core.exceptions import ImproperlyConfigured


def _resolve_app_label():
    try:
        return getattr(django_settings, 'CROPDUSTER_V4_APP_LABEL')
    except AttributeError:
        return getattr(django_settings, 'CROPDUSTER_APP_LABEL', 'cropduster')


def _resolve_db_prefix():
    try:
        return getattr(django_settings, 'CROPDUSTER_V4_DB_PREFIX')
    except AttributeError:
        return getattr(django_settings, 'CROPDUSTER_DB_PREFIX', 'cropduster4')


CROPDUSTER_APP_LABEL = _resolve_app_label()
CROPDUSTER_DB_PREFIX = _resolve_db_prefix()
CROPDUSTER_V4_APP_LABEL = CROPDUSTER_APP_LABEL
CROPDUSTER_V4_DB_PREFIX = CROPDUSTER_DB_PREFIX


def default_jpeg_quality(width, height):
    """JPEG quality as a function of pixel count."""
    pixels = math.sqrt(width * height)
    if pixels >= 1750:
        return 80
    if pixels >= 1000:
        return 85
    return 90


class CropDusterSettings:
    """Read Cropduster configuration from the current Django settings."""

    _MISSING = object()

    def __init__(self):
        self._gifsicle_path = self._MISSING

    def reset(self, **kwargs):
        self._gifsicle_path = self._MISSING

    @property
    def CROPDUSTER_MEDIA_ROOT(self):
        return getattr(
            django_settings, 'CROPDUSTER_MEDIA_ROOT', django_settings.MEDIA_ROOT)

    @property
    def CROPDUSTER_PREVIEW_WIDTH(self):
        return getattr(django_settings, 'CROPDUSTER_PREVIEW_WIDTH', 800)

    @property
    def CROPDUSTER_PREVIEW_HEIGHT(self):
        return getattr(django_settings, 'CROPDUSTER_PREVIEW_HEIGHT', 500)

    @property
    def CROPDUSTER_JPEG_QUALITY(self):
        return getattr(
            django_settings, 'CROPDUSTER_JPEG_QUALITY', default_jpeg_quality)

    @property
    def JPEG_SAVE_ICC_SUPPORTED(self):
        return getattr(django_settings, 'JPEG_SAVE_ICC_SUPPORTED', True)

    @property
    def CROPDUSTER_GIFSICLE_PATH(self):
        path = getattr(django_settings, 'CROPDUSTER_GIFSICLE_PATH', None)
        if path is not None:
            return path
        if self._gifsicle_path is self._MISSING:
            self._gifsicle_path = shutil.which('gifsicle')
        return self._gifsicle_path

    @property
    def CROPDUSTER_RETAIN_METADATA(self):
        return getattr(django_settings, 'CROPDUSTER_RETAIN_METADATA', False)

    @property
    def CROPDUSTER_CREATE_THUMBS(self):
        return getattr(django_settings, 'CROPDUSTER_CREATE_THUMBS', True)

    @property
    def CROPDUSTER_URL_RENDERER(self):
        from cropduster.renderers import DEFAULT_RENDERER

        return getattr(
            django_settings, 'CROPDUSTER_URL_RENDERER', DEFAULT_RENDERER)

    @property
    def CROPDUSTER_THUMBOR(self):
        return getattr(django_settings, 'CROPDUSTER_THUMBOR', None) or {}

    @property
    def CROPDUSTER_REMOTE_IMAGE_FETCH(self):
        """Whether a client may request a server-side download of an image
        URL."""
        return getattr(django_settings, 'CROPDUSTER_REMOTE_IMAGE_FETCH', True)

    @property
    def CROPDUSTER_API_PERMISSION(self):
        return getattr(
            django_settings, 'CROPDUSTER_API_PERMISSION',
            'cropduster.api.permissions.staff_and_object_perm')

    @property
    def CROPDUSTER_LEGACY_CSRF_EXEMPT(self):
        return getattr(
            django_settings, 'CROPDUSTER_LEGACY_CSRF_EXEMPT', True)

    @property
    def CROPDUSTER_DIALOG_MODE(self):
        """Default crop dialog presentation."""
        return getattr(django_settings, 'CROPDUSTER_DIALOG_MODE', 'window')

    @property
    def CROPDUSTER_DEV_SERVER_URL(self):
        return getattr(django_settings, 'CROPDUSTER_DEV_SERVER_URL', None)

    CROPDUSTER_APP_LABEL = CROPDUSTER_APP_LABEL
    CROPDUSTER_DB_PREFIX = CROPDUSTER_DB_PREFIX
    CROPDUSTER_V4_APP_LABEL = CROPDUSTER_V4_APP_LABEL
    CROPDUSTER_V4_DB_PREFIX = CROPDUSTER_V4_DB_PREFIX

    def get_jpeg_quality(self, width, height):
        quality = self.CROPDUSTER_JPEG_QUALITY
        if callable(quality):
            return quality(width, height)
        if isinstance(quality, (int, float)):
            return quality
        raise ImproperlyConfigured(
            'CROPDUSTER_JPEG_QUALITY setting must be either a callable '
            'or a numeric value, got type %s' % type(quality).__name__)


settings = CropDusterSettings()

SETTING_NAMES = tuple(sorted(
    name for name in dir(settings)
    if name.isupper() and not name.startswith('_')))

__all__ = ('default_jpeg_quality', 'get_jpeg_quality', 'settings') + SETTING_NAMES


def get_jpeg_quality(width, height):
    return settings.get_jpeg_quality(width, height)


def __getattr__(name):
    try:
        return getattr(settings, name)
    except AttributeError:
        raise AttributeError("module %r has no attribute %r" % (__name__, name))


def __dir__():
    return sorted(set(globals()) | set(__all__))
