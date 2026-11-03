"""Return URLs for rendition files written by Cropduster."""

import time
from urllib.parse import urlsplit

from cropduster.renderers import BaseRenderer


#: ``?mod=<mktime>``, the format ``Thumb.cache_safe_url`` has always emitted.
CACHE_BUSTER_MOD = "mod"

#: ``?<mktime without its trailing ".0">``, the format historically returned
#: by ``get_crop``. This remains separate from ``CACHE_BUSTER_MOD`` because
#: existing templates and downstream caches use both forms.
CACHE_BUSTER_LEGACY = "legacy"

CACHE_BUSTERS = (CACHE_BUSTER_MOD, CACHE_BUSTER_LEGACY, None)

#: Distinguishes an omitted ``cache_buster`` from an explicit ``"mod"`` so
#: ``for_templatetag()`` can keep the template tags' historical default.
UNSET = object()


class FileRenderer(BaseRenderer):
    """Return URLs for crops that Cropduster wrote to storage.

    Stored renditions have fixed dimensions. For ``multiplier=2``, the
    renderer searches for a sibling thumb twice the size (see
    :meth:`find_density_sibling`). ``max_size=True`` has no separate stored
    file and therefore returns the 1x URL.

    :param cache_buster: ``"mod"`` for ``?mod=<timestamp>``, ``"legacy"`` for
        the bare ``?<timestamp>`` the templatetags emit, or None for no cache
        buster. An explicit value is used for every call. When omitted,
        ``Thumb.cache_safe_url`` uses ``"mod"`` while the template tags retain
        their ``"legacy"`` format. Storage URLs that already contain a query
        are returned unchanged because the query may contain a signature.
    """

    supports_metadata_only = False

    def __init__(self, cache_buster=UNSET):
        self.cache_buster_configured = cache_buster is not UNSET
        if not self.cache_buster_configured:
            cache_buster = CACHE_BUSTER_MOD
        elif cache_buster not in CACHE_BUSTERS:
            from cropduster.exceptions import CropDusterConfigurationError

            raise CropDusterConfigurationError(
                "FileRenderer's `cache_buster` option must be one of %r, got %r." % (
                    CACHE_BUSTERS, cache_buster))
        self.cache_buster = cache_buster

    def for_templatetag(self):
        if self.cache_buster_configured:
            return self
        try:
            return self._templatetag_renderer
        except AttributeError:
            self._templatetag_renderer = type(self)(cache_buster=CACHE_BUSTER_LEGACY)
            return self._templatetag_renderer

    def url(self, thumb, *, image=None, multiplier=1, max_size=False, tmp=False,
            thumbs=None, **opts):
        if image is None:
            image = getattr(thumb, 'image', None)
        if multiplier != 1:
            thumb = self.find_density_sibling(thumb, multiplier, image=image, thumbs=thumbs)
            if thumb is None:
                return None
        # Before an Image is saved, its thumbs are stored under a `_tmp`
        # suffix.
        tmp = bool(tmp) or not getattr(image, 'pk', None)
        return self._file_url(image, thumb.name, tmp=tmp, modified=thumb.date_modified)

    def preview_url(self, image, *, tmp=False, **opts):
        return self._file_url(
            image, 'preview', tmp=tmp, modified=getattr(image, 'date_modified', None))

    def original_url(self, image, *, tmp=False, **opts):
        return self._file_url(
            image, 'original', tmp=tmp, modified=getattr(image, 'date_modified', None))

    def _file_url(self, image, size_name, tmp=False, modified=None):
        from cropduster.models import Image

        image_file = Image.get_file_for_size(image, size_name, tmp=tmp)
        url = image_file.url if image_file else ''
        return self._add_cache_buster(url, modified)

    def _add_cache_buster(self, url, modified):
        if not self.cache_buster or modified is None:
            return url
        parts = urlsplit(url)
        if parts.query:
            return url
        timestamp = time.mktime(modified.timetuple())
        if self.cache_buster == CACHE_BUSTER_LEGACY:
            query = str(timestamp)[:-2]
        else:
            query = "mod=%d" % timestamp
        return parts._replace(query=query).geturl()

    def find_density_sibling(self, thumb, multiplier, image=None, thumbs=None):
        """Return a sibling ``multiplier`` times larger than ``thumb``.

        Higher-density renditions are stored as ordinary sizes. The renderer
        finds them using these rules, in order:

        1. an exact name match on ``<name>@<N>x``, the convention cropduster's
           own size sets use;
        2. dimensions that are exactly N times this thumb's, preferring a
           sibling drawn from the same crop (the same ``reference_thumb``, or
           the parent/child pair) when several match.
        """
        if thumbs is None:
            if image is None:
                image = getattr(thumb, 'image', None)
            # An unsaved image has no reverse relation to query, so its
            # siblings can only come from the caller.
            if image is None or not getattr(image, 'pk', None):
                return None
            thumbs = image.thumbs.all()
        if not thumb.width or not thumb.height:
            return None

        # Use only local columns; resolving each sibling's reference_thumb
        # relation would add a query per thumb. Compare identity rather than
        # primary keys because every unsaved thumb has a None primary key.
        siblings = [t for t in thumbs if t is not thumb]

        by_name = "%s@%sx" % (thumb.name, multiplier)
        for sibling in siblings:
            if sibling.name == by_name:
                return sibling

        target = (thumb.width * multiplier, thumb.height * multiplier)
        matches = [t for t in siblings if (t.width, t.height) == target]
        if not matches:
            return None
        ref_id = thumb.reference_thumb_id or thumb.pk
        matches.sort(key=lambda t: (t.reference_thumb_id or t.pk) != ref_id)
        return matches[0]
