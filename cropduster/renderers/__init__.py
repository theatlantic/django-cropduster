"""Select the backend that converts ``Thumb`` rows to image URLs.

:class:`~cropduster.renderers.file.FileRenderer` returns URLs for rendition
files written by Cropduster. :class:`~cropduster.renderers.thumbor.ThumborRenderer`
returns Thumbor URLs that render from the original, so it does not require
those files when ``CROPDUSTER_CREATE_THUMBS`` is false.

The backend is chosen by ``CROPDUSTER_URL_RENDERER``, either as a dotted path
or as a dict::

    CROPDUSTER_URL_RENDERER = {
        "BACKEND": "cropduster.renderers.ThumborRenderer",
        "OPTIONS": {"server": "https://thumb.example.com/"},
    }

``OPTIONS`` are passed to the backend constructor. Instances are cached by
specification, and the cache is cleared on ``setting_changed`` so that
``override_settings`` takes effect.
"""

from django.utils.module_loading import import_string

from cropduster.conf import settings as cropduster_settings
from cropduster.exceptions import CropDusterConfigurationError


__all__ = (
    'BaseRenderer', 'FileRenderer', 'ThumborRenderer',
    'get_renderer', 'reset_renderer_cache')


DEFAULT_RENDERER = "cropduster.renderers.FileRenderer"


def _density_suffix(density):
    """``2`` -> ``"2x"``, ``1.5`` -> ``"1.5x"``."""
    if isinstance(density, float) and density.is_integer():
        density = int(density)
    return "%sx" % (density,)


class BaseRenderer(object):
    """Define the interface implemented by image URL renderers.

    ``url()`` returns ``None`` when a crop cannot be rendered at the requested
    size. This occurs for legacy rows without crop coordinates and when the
    crop box is too small for a requested density. Callers should omit that
    candidate rather than treat it as an error.
    """

    #: Whether the backend can render crops when
    #: ``CROPDUSTER_CREATE_THUMBS = False`` and no rendition files exist.
    #: ``cropduster.W002`` checks this value.
    supports_metadata_only = False

    def url(self, thumb, *, image=None, multiplier=1, max_size=False, tmp=False,
            thumbs=None, **opts):
        """Return the URL for ``thumb``, or ``None`` if it cannot be rendered.

        :param image: the ``Image`` the thumb belongs to. Pass it whenever it
            is already available to avoid a query. It is required for an
            unsaved ``Thumb``, which has no foreign key to follow.
        :param multiplier: requested pixel density. ``2`` requests a
            double-resolution rendition and returns ``None`` if it is absent.
        :param max_size: render at the crop box's own resolution, ignoring the
            thumb's dimensions.
        :param tmp: use the temporary filename written before the ``Image`` is
            saved.
        :param thumbs: the other thumbs belonging to ``image``. With a
            prefetched collection, ``FileRenderer`` does not read the
            relation again while finding density variants.
        :param opts: backend-specific options.
        """
        raise NotImplementedError

    def srcset(self, thumb, *, image=None, densities=(1, 2), thumbs=None, **opts):
        """Return an ``srcset`` value for ``densities``, or ``None``.

        A density is omitted when the renderer returns no URL for it. If the
        1x URL is missing, the entire result is ``None``.
        """
        candidates = []
        for density in densities:
            url = self.url(
                thumb, image=image, multiplier=density, thumbs=thumbs, **opts)
            if url is None:
                if density == 1:
                    return None
                continue
            if density == 1:
                candidates.append(url)
            else:
                candidates.append("%s %s" % (url, _density_suffix(density)))
        return ", ".join(candidates) or None

    def preview_url(self, image, **opts):
        """Return the downscaled preview URL used by the crop UI."""
        raise NotImplementedError

    def preview_srcset(self, image, *, width, height):
        """Return a higher-density preview candidate, or ``None``.

        A stored-file renderer has only the one ``_preview`` file, so the
        default is ``None``. A renderer that can create a larger preview on
        demand may override this method after checking that the original has
        enough pixels.
        """
        return None

    def original_url(self, image, **opts):
        """Return the URL of the uncropped original."""
        raise NotImplementedError

    def for_templatetag(self):
        """Return the renderer used by the Cropduster template tags.

        Most backends return ``self``. ``FileRenderer`` instead preserves the
        cache-buster format historically returned by ``{% get_crop %}`` and
        ``{% get_thumbs %}``, which differs from ``Thumb.cache_safe_url``.
        """
        return self


def _freeze(value):
    """Convert a renderer specification to a hashable cache key."""
    if isinstance(value, dict):
        return ('dict', tuple(sorted((k, _freeze(v)) for k, v in value.items())))
    if isinstance(value, (list, tuple)):
        return ('seq', tuple(_freeze(v) for v in value))
    return value


_renderer_cache = {}


def get_renderer(spec=None):
    """
    The renderer for ``spec``, defaulting to ``CROPDUSTER_URL_RENDERER``.

    ``spec`` is a dotted path or a ``{"BACKEND": ..., "OPTIONS": {...}}`` dict.
    """
    if spec is None:
        spec = cropduster_settings.CROPDUSTER_URL_RENDERER

    try:
        key = _freeze(spec)
        hash(key)
    except TypeError:
        # A callable argument or storage instance may not be hashable. Build a
        # new renderer rather than caching it under an incomplete key.
        return _build_renderer(spec)

    try:
        return _renderer_cache[key]
    except KeyError:
        renderer = _renderer_cache[key] = _build_renderer(spec)
        return renderer


def _build_renderer(spec):
    options = {}
    if isinstance(spec, dict):
        try:
            path = spec['BACKEND']
        except KeyError:
            raise CropDusterConfigurationError(
                "CROPDUSTER_URL_RENDERER is a dict without a 'BACKEND' key.")
        options = spec.get('OPTIONS') or {}
    else:
        path = spec

    try:
        renderer_cls = import_string(path)
    except ImportError as e:
        raise CropDusterConfigurationError(
            "CROPDUSTER_URL_RENDERER %r could not be imported: %s" % (path, e))

    return renderer_cls(**options)


def reset_renderer_cache(**kwargs):
    """Clear renderer instances after Django sends ``setting_changed``."""
    _renderer_cache.clear()


from .file import FileRenderer  # noqa: E402
from .thumbor import ThumborRenderer  # noqa: E402
