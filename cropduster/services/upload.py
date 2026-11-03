"""Validate an upload and write its original and preview files.

:func:`store_upload` checks the image dimensions against the requested sizes,
writes the original to its own directory, calculates its hash, and creates a
preview for the crop UI. A standalone upload also creates the
``StandaloneImage`` and ``Image`` rows used to store its metadata.

These functions do not depend on forms, HTTP requests, or response formats.
The legacy views, JSON API, and programmatic callers use the same storage
operations.
"""

import hashlib
import os
import posixpath
from dataclasses import dataclass, field, replace
from io import BytesIO

import PIL.Image

from django.contrib.contenttypes.models import ContentType
from django.utils.encoding import force_str

from generic_plus.utils import get_relative_media_url

from cropduster.conf import settings as cropduster_settings
from cropduster.exceptions import CropDusterImageException, ImageTooSmallError
from cropduster.models import Image, StandaloneImage, Thumb
from cropduster.resizing import Size
from cropduster.services.paths import unique_upload_dir
from cropduster.standalone import require_standalone
from cropduster.utils import (
    get_image_extension, get_min_size, has_animated_gif_support, is_animated_gif,
    json, process_image)
from cropduster.utils.storage import get_image_storage


__all__ = (
    'PreviewInfo', 'UploadResult', 'store_upload', 'adopt_standalone',
    'min_upload_size', 'normalize_sizes', 'preview_dimensions',
    'open_stored_image', 'ANIMATED_GIF_WARNING')


#: Warning returned when an animated GIF is stored without gifsicle support.
#: The JSON API retains the code, while the legacy response uses the message.
ANIMATED_GIF_WARNING = {
    'code': 'animated_gif_no_gifsicle',
    'message': (
        "This server does not have animated gif support; your uploaded image "
        "has been made static."),
}


@dataclass
class PreviewInfo:
    """Describe the dimensions of the preview used by the crop UI."""

    width: int
    height: int


@dataclass
class UploadResult:
    """Describe the files and rows created for an upload.

    ``image`` remains unsaved for an ordinary upload because its containing
    object is not known until the form is saved. A standalone image belongs to
    a ``StandaloneImage`` row immediately, so both rows are saved before the
    result is returned.
    """

    image: Image
    original_name: str
    width: int
    height: int
    md5: str
    preview: PreviewInfo | None = None
    standalone_image: StandaloneImage | None = None
    standalone_thumb: Thumb | None = None
    #: Sizes used to validate the upload. Standalone mode replaces this list
    #: with the size assigned to its initial crop.
    sizes: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


def store_upload(file, *, upload_to=None, sizes=None, preview_size=None,
                 preview=True, standalone=False, for_size=None):
    """
    Validate ``file``, write it to storage, and describe what was stored.

    :param upload_to: a ``FileField`` strftime pattern or callable naming the
        parent of the upload directory.
    :param sizes: the sizes the image has to be big enough for. A list of
        :class:`~cropduster.resizing.Size`, the JSON form of one, or None to
        skip the minimum-dimension check.
    :param preview_size: ``(width, height)`` bounding box for the preview; each
        may be ``None`` to use the corresponding ``CROPDUSTER_PREVIEW_*``
        setting.
    :param preview: whether to write a preview for an ordinary upload. In
        standalone mode the preview is always deferred until deduplication
        selects the retained image.
    :param standalone: also create the standalone rows and the initial
        full-image crop (see :func:`adopt_standalone`).
    :param for_size: validate the minimum dimensions against the one size of
        that name rather than all of them. This permits a replacement source
        for one crop even if it cannot satisfy unrelated sizes.
    :raises ImageTooSmallError: the image is smaller than ``sizes`` require.
    :raises CropDusterImageException: the file is not a usable image.
    """
    if standalone:
        # Check metadata support before writing the original so a missing
        # optional dependency does not leave an incomplete upload.
        require_standalone()

    storage = get_image_storage()
    sizes = normalize_sizes(sizes)

    file.seek(0)
    try:
        uploaded_image = PIL.Image.open(file)
    except IOError as e:
        raise CropDusterImageException(
            force_str(e) if e.errno else "Invalid or unsupported image file")
    extension = get_image_extension(uploaded_image)

    orig_w, orig_h = uploaded_image.size
    min_w, min_h = min_upload_size(sizes, for_size=for_size)
    if orig_w < min_w or orig_h < min_h:
        raise ImageTooSmallError((min_w, min_h), (orig_w, orig_h))
    if orig_w <= 0:
        raise CropDusterImageException("Invalid image: width is %d" % orig_w)
    elif orig_h <= 0:
        raise CropDusterImageException("Invalid image: height is %d" % orig_h)

    folder_path = unique_upload_dir(file.name, upload_to, storage=storage)

    file.seek(0)
    original_name = get_relative_media_url(
        storage.save(posixpath.join(folder_path, 'original' + extension), file))

    md5_hash = hashlib.md5()
    with storage.open(original_name) as f:
        md5_hash.update(f.read())

    # With dimensions supplied, the image field does not reopen the file
    # through its configured storage, which may differ from ``storage`` here.
    image = Image(image=original_name, width=orig_w, height=orig_h)
    pil_image = open_stored_image(image.image.name, storage=storage)
    width, height = pil_image.size

    warnings = []
    if is_animated_gif(pil_image) and not has_animated_gif_support():
        warnings.append(dict(ANIMATED_GIF_WARNING))

    result = UploadResult(
        image=image,
        original_name=original_name,
        width=width,
        height=height,
        md5=md5_hash.hexdigest(),
        preview=(
            _write_preview(image, pil_image, preview_size, storage=storage)
            if preview and not standalone else None),
        sizes=sizes,
        warnings=warnings)

    if standalone:
        result = adopt_standalone(
            result, sizes=sizes, preview_size=preview_size, storage=storage)
    return result


def adopt_standalone(result, *, sizes=None, preview_size=None, storage=None):
    """Create the database rows and initial crop for a standalone upload.

    Standalone images are deduplicated by MD5. If the same bytes were uploaded
    earlier, the result uses the original ``Image`` row and deletes the newly
    stored copy. The initial crop covers the complete image but remains unsaved
    until the client accepts it.

    The preview is written after deduplication and only when the retained image
    does not have one. This ensures that its URL belongs to the image returned
    to the crop UI rather than the duplicate upload.
    """
    require_standalone()
    storage = storage or get_image_storage()
    sizes = normalize_sizes(sizes)

    original_name = result.original_name

    standalone_image, _created = StandaloneImage.objects.get_or_create(
        md5=result.md5, defaults={'image': original_name})

    image = Image.objects.get_or_create(
        content_type=ContentType.objects.get_for_model(StandaloneImage),
        object_id=standalone_image.pk)[0]

    if not image.image:
        image.image = original_name
        image.save()
    elif image.image.name != original_name:
        storage.delete(original_name)
        try:
            os.rmdir(os.path.dirname(storage.path(original_name)))
        except (NotImplementedError, OSError):
            pass
        original_name = image.image.name

    pil_image = open_stored_image(image.image.name, storage=storage)
    if not image.width or not image.height:
        # Read dimensions for rows created before the width and height fields
        # were added.
        image.width, image.height = pil_image.size
    preview = _write_preview(
        image, pil_image, preview_size, storage=storage, skip_existing=True,
        source_size=(result.width, result.height))

    thumb = image.save_size(
        Size('crop', w=pil_image.size[0], h=pil_image.size[1]),
        image=pil_image, standalone=True, commit=False)

    # Preserve the single requested size. With multiple or no sizes, a
    # generic crop is used because the initial crop cannot be assigned
    # unambiguously.
    size = sizes[0] if len(sizes) == 1 else Size('crop')

    return replace(
        result,
        image=image,
        original_name=original_name,
        preview=preview,
        standalone_image=standalone_image,
        standalone_thumb=thumb,
        sizes=[size])


def normalize_sizes(sizes):
    """Return ``sizes`` as a list of ``Size`` objects.

    The widget stores sizes as JSON in a form field. Parsing that value through
    :mod:`cropduster.utils.jsonutils` reconstructs the serialized
    :class:`~cropduster.resizing.Size` instances.
    """
    if isinstance(sizes, str):
        sizes = json.loads(sizes)
    return list(sizes or [])


def min_upload_size(sizes, *, for_size=None):
    """Return the minimum dimensions required by ``sizes``.

    ``for_size`` restricts the calculation to one named size and its automatic
    children.
    """
    sizes = normalize_sizes(sizes)
    if not sizes:
        return (0, 0)
    if for_size is not None:
        sizes = [_find_size(sizes, for_size)]
    return get_min_size(sizes)


def preview_dimensions(size, bounds):
    """Scale ``size`` down to ``bounds`` without enlarging it."""
    (w, h), (max_w, max_h) = size, bounds
    if not w or not h:
        return (max_w, max_h)
    ratio = min(max_w / w, max_h / h)
    if ratio >= 1:
        return (w, h)
    return (int(round(w * ratio)), int(round(h * ratio)))


def preview_bounds(preview_size=None):
    """Fill missing preview bounds from the Cropduster settings."""
    width, height = preview_size or (None, None)
    return (
        width or cropduster_settings.CROPDUSTER_PREVIEW_WIDTH,
        height or cropduster_settings.CROPDUSTER_PREVIEW_HEIGHT)


def _find_size(sizes, name):
    for size in Size.flatten(sizes):
        if size.name == name:
            return size
    raise ValueError(
        "No size named %r among %r." % (
            name, [getattr(s, 'name', s) for s in Size.flatten(sizes)]))


def open_stored_image(name, *, storage=None):
    """Read a storage-relative image into a PIL image."""
    storage = storage or get_image_storage()
    with storage.open(name, mode='rb') as f:
        pil_image = PIL.Image.open(BytesIO(f.read()))
        pil_image.filename = f.name
    return pil_image


def _write_preview(image, pil_image, preview_size, *, storage=None,
                   skip_existing=False, source_size=None):
    """Write a preview next to the original and return its dimensions and URL.

    ``source_size`` supplies the dimensions used to calculate the scale. A
    deduplicated standalone upload uses the dimensions of the current upload
    while writing the retained image's preview.
    """
    storage = storage or image.storage
    bounds = preview_bounds(preview_size)
    width, height = preview_dimensions(source_size or pil_image.size, bounds)
    preview_path = image.get_image_path('_preview')

    if not (skip_existing and storage.exists(preview_path)):
        process_image(
            pil_image, preview_path, _preview_fitter(source_size or pil_image.size, bounds),
            storage=storage)

    return PreviewInfo(width=width, height=height)


def _preview_fitter(source_size, bounds):
    (w, h), (max_w, max_h) = source_size, bounds
    ratio = min(max_w / w, max_h / h) if (w and h) else 1

    def fit_preview(im):
        if ratio >= 1:
            return im
        w, h = im.size
        return im.resize(
            (int(round(w * ratio)), int(round(h * ratio))), PIL.Image.LANCZOS)

    return fit_preview
