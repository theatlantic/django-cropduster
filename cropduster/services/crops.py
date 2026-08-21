"""Choose a crop box for a size and create its unsaved ``Thumb``.

Code that creates crops without the dialog must select from the boxes already
drawn on the image. This includes :func:`~cropduster.services.attach.attach`,
copies between fields, and migrations that add a size to existing images.

:func:`choose_crop` fits the requested size to each candidate and compares the
result with the original box using intersection over union
(:func:`crop_overlap`). The greatest overlap retains the most of the existing
framing. :func:`thumb_for_size` converts that result to an unsaved ``Thumb``.

These functions use dimensions rather than pixel data, so they also work
when ``CROPDUSTER_CREATE_THUMBS = False`` and no rendition file exists to
read.
"""

from cropduster.resizing import Box, Crop, image_size as resolve_image_size


__all__ = ('crop_overlap', 'choose_crop', 'thumb_for_size')


def crop_overlap(c1, c2):
    """Return the intersection-over-union score for two crops.

    ``0.0`` for crops that do not overlap at all, ``1.0`` for identical ones.
    """
    b1, b2 = c1.box, c2.box
    area_1 = b1.w * b1.h
    area_2 = b2.w * b2.h

    x1 = max(b1.x1, b2.x1)
    x2 = min(b1.x2, b2.x2)
    y1 = max(b1.y1, b2.y1)
    y2 = min(b1.y2, b2.y2)
    if x1 >= x2 or y1 >= y2:
        return 0.0

    intersection_area = (x2 - x1) * (y2 - y1)
    union_area = area_1 + area_2 - intersection_area

    return intersection_area / union_area


def choose_crop(image, size, *, candidates=None, hint=None, image_size=None):
    """Return the existing crop that best fits ``size``.

    :param candidates: the boxes to choose between, as ``Crop``, ``Thumb`` or
        ``Box``. Defaults to the image's top-level crops: the ones an editor
        drew, as opposed to the ``auto`` sizes that follow them.
    :param hint: a crop to use instead of choosing one. A ``Crop``, a ``Thumb``,
        a ``Box``, an ``(x, y, w, h)`` tuple, or the name of one of the image's
        crops.
    :param image_size: the ``(width, height)`` the boxes are measured against,
        for an image whose own dimensions are not filled in.

    Return ``None`` when there are no usable candidates; callers can then use
    the complete image.
    """
    dimensions = _dimensions(image, image_size)

    if hint is not None:
        return as_crop(hint, dimensions, image=image)

    if candidates is None:
        candidates = _drawn_crops(image)
    crops = [as_crop(candidate, dimensions, image=image) for candidate in candidates]
    crops = [crop for crop in crops if crop is not None]
    if not crops:
        return None

    # max() returns the first of equally scored crops, so the reversed
    # iteration selects the newest one.
    return max(
        reversed(crops),
        key=lambda crop: crop_overlap(size.fit_to_crop(crop), crop))


def thumb_for_size(image, size, *, best_crop=None, image_size=None):
    """Return an unsaved ``Thumb`` for ``size``, or ``None`` if it cannot fit.

    The box comes from ``best_crop``, or from :func:`choose_crop`, or (when
    the image has no crops to choose between) from the whole frame. It is
    then fitted to the size, and the fit enforces the size's aspect ratio and
    its minimum and maximum dimensions.

    The result is ``None`` when the image or fitted box is smaller than the
    requested size. A saved image is assigned to the thumb; an unsaved image
    has no primary key and leaves the thumb unattached.

    :param image_size: the ``(width, height)`` to measure against, for an image
        whose own dimensions are not filled in.
    """
    from cropduster.models import Thumb

    orig_w, orig_h = _dimensions(image, image_size)

    if size.w and size.w > orig_w:
        return None
    if size.h and size.h > orig_h:
        return None

    if best_crop is None:
        best_crop = (
            choose_crop(image, size, image_size=(orig_w, orig_h))
            or Crop(Box(0, 0, orig_w, orig_h), (orig_w, orig_h)))

    # The fitted box has the size's shape; how far it can be scaled down is
    # still bounded by the pixels inside it and by the image around it.
    new_crop = size.fit_to_crop(best_crop)

    width, height = size.w, size.h
    if not width and not height:
        width, height = new_crop.box.size
    elif not width:
        width = new_crop.box.w * (height / new_crop.box.h)
        width = min(int(round(width)), new_crop.bounds.w)
    elif not height:
        height = new_crop.box.h * (width / new_crop.box.w)
        height = min(int(round(height)), new_crop.bounds.h)

    new_w, new_h = new_crop.box.size
    if new_w < width or new_h < height:
        return None

    max_scales = []
    if size.max_w and size.max_w < width:
        max_scales.append(size.max_w / width)
    if size.max_h and size.max_h < height:
        max_scales.append(size.max_h / height)
    if max_scales:
        max_scale = min(max_scales)
        width = int(round(width * max_scale))
        height = int(round(height * max_scale))

    thumb = Thumb(
        name=size.name,
        image=image if getattr(image, 'pk', None) else None,
        width=width,
        height=height)
    if not size.is_auto:
        # An auto size has no box of its own; it follows its reference
        # thumb's, best-fitted at render time.
        thumb.crop_x = new_crop.box.x1
        thumb.crop_y = new_crop.box.y1
        thumb.crop_w = new_crop.box.w
        thumb.crop_h = new_crop.box.h
    return thumb


def as_crop(value, image_size, *, image=None):
    """Convert ``value`` to a crop measured against ``image_size``.

    Accepts a ``Crop``, a ``Thumb``, a ``Box``, an ``(x, y, w, h)`` tuple, or
    the name of one of ``image``'s crops. Returns ``None`` for a thumb with
    no crop box, the state of legacy rows and auto sizes.
    """
    from cropduster.models import Thumb

    if value is None:
        return value
    if isinstance(value, Crop):
        return value if _positive_box(value.box) else None
    if isinstance(value, str):
        value = _named_thumb(image, value)
    if isinstance(value, Thumb):
        box = value.get_crop_box()
        return None if box is None or not _positive_box(box) else Crop(box, image_size)
    if isinstance(value, Box):
        return Crop(value, image_size) if _positive_box(value) else None
    if isinstance(value, (tuple, list)) and len(value) == 4:
        x, y, w, h = value
        box = Box(x, y, x + w, y + h)
        return Crop(box, image_size) if _positive_box(box) else None
    raise ValueError(
        "Cannot read a crop from %r. Pass a Crop, a Thumb, a Box, an "
        "(x, y, w, h) tuple, or the name of one of the image's crops." % (value,))


def _positive_box(box):
    return box.w > 0 and box.h > 0


def _named_thumb(image, name):
    thumb = (
        image.thumbs.filter(name=name).first()
        if getattr(image, 'pk', None) else None)
    if thumb is None:
        raise ValueError("%r has no crop named %r." % (image, name))
    return thumb


def _drawn_crops(image):
    """Return top-level crops in a stable, oldest-to-newest order.

    :func:`choose_crop` uses the most recent row when scores are equal, so the
    query is ordered by primary key rather than database-dependent row order.
    """
    if not getattr(image, 'pk', None):
        return []
    return list(image.thumbs.filter(reference_thumb__isnull=True).order_by('pk'))


def _dimensions(image, image_size=None):
    return resolve_image_size(image if image_size is None else image_size)
