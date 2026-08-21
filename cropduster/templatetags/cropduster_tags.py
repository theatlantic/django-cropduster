import warnings

from django import template

from cropduster.models import prime_reference_thumbs
from cropduster.renderers import get_renderer
from cropduster.utils.sizes import sanitize_size_name


register = template.Library()


def _thumbs_for(image):
    """Return an image's thumbs with their crop references cached.

    Both tags read each crop through ``reference_thumb``; without the cache,
    each access adds a query even when the thumbs were prefetched with the
    image.
    """
    thumbs = list(image.thumbs.all())
    prime_reference_thumbs(thumbs)
    return thumbs


def _crop_box(thumb):
    """Return the thumb's crop box as a dictionary, or ``None``."""
    get_crop_box = getattr(thumb, 'get_crop_box', None)
    box = get_crop_box() if get_crop_box else None
    if box is None:
        return None
    return {
        'x1': box.x1, 'y1': box.y1, 'x2': box.x2, 'y2': box.y2,
        'width': box.w, 'height': box.h,
    }


def _thumb_context(image, thumb, url, srcset):
    return {
        "url": url,
        "srcset": srcset,
        "width": thumb.width,
        "height": thumb.height,
        "thumb": thumb,
        "crop": _crop_box(thumb),
        "attribution": image.attribution,
        "attribution_link": image.attribution_link,
        "caption": image.caption,
        "alt_text": image.alt_text,
    }


@register.simple_tag
def get_crop(image, crop_name, **kwargs):
    """Return one named crop of an image.

    Usage::

        {% get_crop article.image 'square_thumbnail' as img %}

    The tag assigns a dictionary like this to ``img``::

        {
            "url": '/media/path/to/my.jpg?1519905601',
            "srcset": '/media/path/to/my.jpg?1519905601, /media/path/to/my@2x.jpg?1519905601 2x',
            "width": 150,
            "height": 150,
            "thumb": <Thumb: square_thumbnail>,
            "crop": {"x1": 0, "y1": 90, "x2": 1240, "y2": 710, "width": 1240, "height": 620},
            "attribution": 'Stock Photoz',
            "attribution_link": 'http://stockphotoz.com',
            "caption": 'Woman laughing alone with salad.',
            "alt_text": 'Woman laughing alone with salad.'
        }

    The result can be used in an image tag or style block::

        <img src="{{ img.url }}" srcset="{{ img.srcset }}">

    ``url`` and ``srcset`` come from the ``CROPDUSTER_URL_RENDERER`` backend
    and are ``None`` when the renderer cannot produce the crop. Passing ``"original"``
    as ``crop_name`` returns the uncropped image, with ``thumb`` set to its
    ``Image`` row and ``crop`` set to ``None``.

    Unknown keyword arguments are ignored for compatibility with older
    templates. ``exact_size`` is deprecated.
    """
    if "exact_size" in kwargs:
        warnings.warn("get_crop's `exact_size` kwarg is deprecated.", DeprecationWarning)

    if not image or not image.related_object:
        return None

    related = image.related_object
    thumbs = _thumbs_for(related)
    renderer = get_renderer().for_templatetag()

    thumb = next((t for t in thumbs if t.name == crop_name), None)
    if thumb is None:
        if crop_name != "original":
            return None
        # The original has no Thumb row. Use the Image for the shared metadata
        # fields and leave its crop box empty.
        url = renderer.original_url(related)
        return _thumb_context(related, related, url, url)

    return _thumb_context(
        related, thumb,
        renderer.url(thumb, image=related, thumbs=thumbs),
        renderer.srcset(thumb, image=related, thumbs=thumbs))


@register.simple_tag
def get_thumbs(image, **kwargs):
    """Return every crop of an image, keyed by size name.

    Usage::

        {% get_thumbs article.image as thumbs %}
        <img src="{{ thumbs.square_thumbnail.url }}">

    Each value has the same fields returned by ``{% get_crop %}``. Size names
    are sanitized for template lookup, so ``main@2x`` is available as
    ``main_2x``. Each ``SizeAlias`` declared on the field adds its own key.

    If two names produce the same sanitized key, only the first name is
    included and a ``RuntimeWarning`` reports the collision.

    The ``metadata`` entry contains the image's ``attribution``,
    ``attribution_link``, ``caption``, and ``alt_text`` values.
    """
    if not image or not image.related_object:
        return {}

    related = image.related_object
    thumbs = _thumbs_for(related)
    renderer = get_renderer().for_templatetag()

    by_key = {}
    for thumb in sorted(thumbs, key=lambda t: (t.name or '', t.pk or 0)):
        by_key.setdefault(sanitize_size_name(thumb.name), []).append(thumb)

    collisions = {key: group for key, group in by_key.items() if len(group) > 1}
    if collisions:
        warnings.warn(
            "Size names collide once sanitized for {%% get_thumbs %%}; only the "
            "first of each is included: %s." % "; ".join(
                "%s <- %s" % (key, ", ".join(t.name for t in group))
                for key, group in sorted(collisions.items())),
            RuntimeWarning)

    data = {
        key: _thumb_context(
            related, group[0],
            renderer.url(group[0], image=related, thumbs=thumbs),
            renderer.srcset(group[0], image=related, thumbs=thumbs))
        for key, group in by_key.items()
    }

    for size in getattr(image, 'sizes', None) or []:
        if getattr(size, 'is_alias', False):
            size.add_to_sizes_dict(data)

    data["metadata"] = {
        "attribution": related.attribution,
        "attribution_link": related.attribution_link,
        "caption": related.caption,
        "alt_text": related.alt_text,
    }
    return data
