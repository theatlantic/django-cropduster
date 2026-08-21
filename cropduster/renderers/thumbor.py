"""Build URLs for a `Thumbor <https://www.thumbor.org/>`_ image server.

Each URL contains the original upload and the stored crop box. Thumbor applies
the crop and resize when the URL is requested, so Cropduster does not need to
write rendition files when ``CROPDUSTER_CREATE_THUMBS = False``.

Configuration is read from one dict::

    CROPDUSTER_THUMBOR = {
        "SERVER": "https://thumb.example.com/",
        "MEDIA_URL": "https://cdn.example.com/media/",
        "SECURITY_KEY": "...",
        "EXTRA_MEDIA_URLS": [],
        "FILTERS": [],
        "SMART": False,
        "FIT_IN": False,
    }

Install the ``thumbor`` extra with
``pip install django-cropduster[thumbor]``.
"""

import functools
import re
import warnings
from urllib.parse import urljoin

from django.conf import settings as django_settings

from cropduster.conf import settings as cropduster_settings
from cropduster.exceptions import CropDusterConfigurationError
from cropduster.renderers import BaseRenderer


#: Root used by Thumbor's source loader. Configured media URLs are replaced
#: with this prefix.
SOURCE_PREFIX = 'media/'

DEFAULTS = {
    'SERVER': None,
    'MEDIA_URL': None,
    'SECURITY_KEY': None,
    'EXTRA_MEDIA_URLS': (),
    'FILTERS': (),
    'SMART': False,
    'FIT_IN': False,
}

#: Legacy top-level settings corresponding to ``CROPDUSTER_THUMBOR`` keys.
LEGACY_SETTINGS = {
    'SERVER': 'THUMBOR_SERVER',
    'MEDIA_URL': 'THUMBOR_MEDIA_URL',
    'SECURITY_KEY': 'THUMBOR_SECURITY_KEY',
}


@functools.lru_cache(maxsize=None)
def _warn_legacy_setting(legacy_name, key):
    warnings.warn(
        "The %s setting is deprecated; put it in CROPDUSTER_THUMBOR[%r] instead."
        % (legacy_name, key),
        DeprecationWarning, stacklevel=2)


def normalize_prefix(url):
    """Return a configured URL with the trailing slash required for joining.

    ``https://cdn.example.com/media`` and ``https://cdn.example.com/media/``
    refer to the same location. The trailing slash is required when removing
    that prefix from a storage URL and when passing it to ``urljoin``.
    """
    if url and not url.endswith('/'):
        return '%s/' % url
    return url


def validate_security_key(key):
    """Reject a security key that cannot be passed to Thumbor's HMAC.

    ``None`` selects unsigned ``/unsafe/`` URLs. Other non-text values would
    raise ``TypeError`` from ``hmac`` when a URL is rendered, so they are
    reported as configuration errors here.
    """
    if key is None or isinstance(key, (str, bytes)):
        return
    raise CropDusterConfigurationError(
        "CROPDUSTER_THUMBOR['SECURITY_KEY'] must be a string, bytes or None, "
        "got %s (%r)." % (type(key).__name__, key))


class ThumborRenderer(BaseRenderer):
    """Return Thumbor crop URLs rendered from the original image.

    Constructor arguments override the corresponding ``CROPDUSTER_THUMBOR``
    values. Renderer ``OPTIONS`` can therefore select a different server
    without changing the project-wide setting.
    """

    supports_metadata_only = True

    def __init__(self, server=None, media_url=None, security_key=None,
                 extra_media_urls=None, filters=None, smart=None, fit_in=None):
        try:
            from libthumbor import CryptoURL  # noqa: F401
        except ImportError as e:
            raise CropDusterConfigurationError(
                "ThumborRenderer needs libthumbor, which is not installed: %s. "
                "Install it with `pip install django-cropduster[thumbor]`." % e)

        config = self.read_settings()
        configured_server = server if server is not None else config['SERVER']
        if not isinstance(configured_server, str) or not configured_server:
            raise CropDusterConfigurationError(
                "CROPDUSTER_THUMBOR['SERVER'] must be a non-empty URL, got %r."
                % configured_server)
        self.server = normalize_prefix(configured_server)
        self.media_url = media_url if media_url is not None else config['MEDIA_URL']
        self.security_key = (
            security_key if security_key is not None else config['SECURITY_KEY'])
        self.extra_media_urls = tuple(
            extra_media_urls if extra_media_urls is not None
            else config['EXTRA_MEDIA_URLS'])
        self.filters = tuple(filters if filters is not None else config['FILTERS'])
        self.smart = bool(smart if smart is not None else config['SMART'])
        self.fit_in = bool(fit_in if fit_in is not None else config['FIT_IN'])

        validate_security_key(self.security_key)

    @staticmethod
    def read_settings():
        """Return Thumbor settings with legacy top-level values applied."""
        configured = cropduster_settings.CROPDUSTER_THUMBOR
        config = dict(DEFAULTS)
        for key in DEFAULTS:
            if key in configured:
                config[key] = configured[key]
                continue
            legacy_name = LEGACY_SETTINGS.get(key)
            if legacy_name is not None and hasattr(django_settings, legacy_name):
                _warn_legacy_setting(legacy_name, key)
                config[key] = getattr(django_settings, legacy_name)
        return config

    def url(self, thumb, *, image=None, multiplier=1, max_size=False, tmp=False,
            thumbs=None, **opts):
        """Return the Thumbor URL for ``thumb``.

        The result is ``None`` in these cases:

        - a top-level thumb has no crop box;
        - a thumb whose reference thumb has no crop box either;
        - ``multiplier`` is greater than 1 and the crop box is smaller than the
          requested rendition;
        - ``multiplier`` is greater than 1 and the thumb has no dimensions.

        ``tmp`` is ignored because Thumbor reads the original, which is stored
        before crop coordinates are saved.
        """
        image = image if image is not None else thumb.image
        if not thumb.reference_thumb_id and not thumb.crop_w:
            return None

        crop_box = thumb.get_crop_box()
        if crop_box is None:
            return None

        x1, y1, x2, y2 = crop_box.as_tuple()
        thumb_w, thumb_h = thumb.width, thumb.height
        crop_w, crop_h = (x2 - x1), (y2 - y1)
        orig_w, orig_h = image.width, image.height

        if max_size:
            thumb_w, thumb_h = crop_w, crop_h
        elif multiplier > 1:
            if not thumb_w or not thumb_h:
                return None
            if crop_w < (thumb_w * multiplier) or crop_h < (thumb_h * multiplier):
                return None
            thumb_w *= multiplier
            thumb_h *= multiplier

        gen_kwargs = {}
        if (x1, y1, x2, y2) != (0, 0, orig_w, orig_h):
            gen_kwargs['crop'] = ((x1, y1), (x2, y2))
        if crop_w != thumb_w or crop_h != thumb_h:
            gen_kwargs.update({'width': thumb_w, 'height': thumb_h})
        gen_kwargs.update(opts)

        return self.image_url(image.image.url, **gen_kwargs)

    def original_url(self, image, **opts):
        return self.image_url(image.image.url, **opts)

    def preview_url(self, image, **opts):
        """Return the original scaled to fit the crop UI preview.

        Metadata-only mode has no ``_preview`` file, so Thumbor creates the
        preview from the original.
        """
        opts.setdefault('fit_in', True)
        opts.setdefault('width', cropduster_settings.CROPDUSTER_PREVIEW_WIDTH)
        opts.setdefault('height', cropduster_settings.CROPDUSTER_PREVIEW_HEIGHT)
        return self.image_url(image.image.url, **opts)

    def preview_srcset(self, image, *, width, height):
        """Return a 2x preview candidate when the original can supply it."""
        image_width, image_height = image.width, image.height
        if not all((width, height, image_width, image_height)):
            return None
        if min(width, height, image_width, image_height) <= 0:
            return None

        width_2x, height_2x = width * 2, height * 2
        if image_width < width_2x or image_height < height_2x:
            return None
        return "%s 2x" % self.preview_url(
            image, width=width_2x, height=height_2x)

    def image_url(self, image_url, filters=None, **kwargs):
        """Return a signed or unsafe Thumbor URL for ``image_url``."""
        from libthumbor import CryptoURL

        # Libthumbor preserves numeric types. Thumbor rejects a URL containing
        # floating-point crop coordinates or dimensions.
        if kwargs.get('crop'):
            ((x1, y1), (x2, y2)) = kwargs['crop']
            kwargs['crop'] = ((int(x1), int(y1)), (int(x2), int(y2)))
        for key in ('width', 'height'):
            if kwargs.get(key) is not None:
                kwargs[key] = int(kwargs[key])

        gen_kwargs = dict({
            'unsafe': not self.security_key,
            'image_url': self.strip_source_prefix(image_url),
            'filters': list(filters if filters is not None else self.filters),
        }, **kwargs)
        if self.smart:
            gen_kwargs.setdefault('smart', True)
        if self.fit_in:
            gen_kwargs.setdefault('fit_in', True)

        url_gen = CryptoURL(key=self.security_key or '')
        rel_url = url_gen.generate(**gen_kwargs)
        if rel_url.startswith('/'):
            rel_url = rel_url[1:]
        joined_url = urljoin(self.server, rel_url)
        # https://bugs.python.org/issue40594: urljoin collapses the `//` of the
        # source URL embedded in the path.
        return re.sub(r'(https?):/(?!/)', r'\1://', joined_url)

    def strip_source_prefix(self, image_url):
        """Convert a storage URL to the path used by Thumbor's loader.

        The source loader maps ``media/...`` to the same bytes returned by the
        configured storage, so a matching media URL is replaced with that
        prefix. Object storage may return a host different from ``MEDIA_URL``;
        ``EXTRA_MEDIA_URLS`` supplies those alternatives. The first matching
        prefix is removed. If none match, the complete URL is returned for
        Thumbor's HTTP loader.
        """
        prefixes = [self.media_url, str(django_settings.MEDIA_URL)]
        prefixes.extend(self.extra_media_urls)
        for prefix in prefixes:
            prefix = normalize_prefix(prefix)
            if prefix and image_url.startswith(prefix):
                return image_url.replace(prefix, SOURCE_PREFIX, 1)
        return image_url
