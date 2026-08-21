"""Attach an image and its crops without using the browser dialog.

:func:`attach` stores an original, selects a crop box for each declared size,
renders the crops, and creates the same ``Image`` and ``Thumb`` rows as the
widget. :func:`copy_image` uses an existing Cropduster image as the source and
copies its metadata and crop framing.

Both functions return :class:`AttachResult`. Its ``payload(legacy=True)`` value
can be passed to ``CropDuster.complete()`` to update a widget without opening
the dialog.

For an unsaved instance, the generic relation has no primary key to reference.
Its crops use temporary filenames and remain unattached ``Thumb`` rows. The
widget posts their primary keys and the formset attaches them when it saves the
instance.
"""

import contextlib
import os
import re
from dataclasses import dataclass, field
from io import BytesIO
from tempfile import SpooledTemporaryFile
from urllib.error import URLError

import PIL.Image

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import SuspiciousOperation
from django.core.files.base import ContentFile, File
from django.db import transaction

from generic_plus.utils import get_relative_media_url

from cropduster.conf import settings as cropduster_settings
from cropduster.exceptions import (
    CropDusterConfigurationError, CropDusterFileMissing, CropDusterResizeException,
    ImageTooSmallError)
from cropduster.files import ImageFile, VirtualFieldFile
from cropduster.models import Image
from cropduster.resizing import Box, Crop, Size, image_size as resolve_image_size
from cropduster.services.crops import as_crop, choose_crop, thumb_for_size
from cropduster.services.crop import CropResult, _SourceOpener, _copy_to_tmp
from cropduster.services.payload import build_payload, legacy_crop_response
from cropduster.services.upload import (
    PreviewInfo, normalize_sizes, preview_bounds, preview_dimensions,
    store_upload, open_stored_image, _write_preview)
from cropduster.utils import get_image_extension, get_min_size
from cropduster.utils.fields import get_cropduster_field
from cropduster.utils.storage import get_image_storage


__all__ = ('AttachResult', 'attach', 'copy_image')


#: ``Image`` fields accepted by ``metadata`` and copied by :func:`copy_image`.
METADATA_FIELDS = ('attribution', 'attribution_link', 'caption', 'alt_text')

#: The geometry a computed crop contributes to the row it is stored in.
GEOMETRY_FIELDS = ('width', 'height', 'crop_x', 'crop_y', 'crop_w', 'crop_h')

#: Matches HTTP and protocol-relative source URLs.
URL_RE = re.compile(r'^(?:https?:)?//')


@dataclass
class AttachResult:
    """Describe the image, crops, and errors produced by :func:`attach`.

    ``thumbs`` includes each rendered size and its ``auto`` children, keyed by
    name. ``errors`` uses the same keys for sizes that could not be rendered.
    The ``permissive`` argument determines whether required-size failures are
    collected there or raised.
    """

    image: Image
    thumbs: dict = field(default_factory=dict)
    errors: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)
    #: Declared sizes used to create the crops.
    sizes: list = field(default_factory=list)
    preview: PreviewInfo | None = None
    #: Whether the crops use temporary filenames until the object is saved.
    tmp: bool = False

    def payload(self, renderer=None, legacy=False, sanitize=False):
        """Return the v1 payload or the legacy widget value.

        By default this calls :func:`~cropduster.services.payload.build_payload`.
        With ``legacy=True``, it returns the value read by
        ``CropDuster.complete()``, including image metadata and a preview of
        the first crop.

        ``sanitize=True`` runs the crop names through
        :func:`~cropduster.utils.sizes.sanitize_size_name`, for consumers that
        subscript them from a template.
        """
        thumbs = self.thumbs
        if self.tmp:
            thumbs = CropResult(
                image=self.image, thumbs=self.thumbs,
                tmp_names=set(self.thumbs))
        payload = build_payload(
            self.image, thumbs=thumbs, sizes=self.sizes,
            preview=self.preview, renderer=renderer,
            warnings=self.warnings)
        if not legacy:
            return payload
        return _legacy_payload(payload, sanitize=sanitize)

    def orphan_thumbs(self):
        """Detach crops so a formset can attach them while saving.

        The widget posts the ``Thumb`` primary keys, and the formset assigns
        those rows to the image created for the saved object.
        """
        for thumb in self.thumbs.values():
            thumb.image = None
            thumb.save()


def attach(instance, field_name, source, *, sizes=None, metadata=None, crops=None,
           sources=None, upload_to=None, preview=True, commit=True, tmp=None,
           permissive=True, skip_existing=False):
    """
    Set a Cropduster field and render its configured sizes.

    :param source: the image. A path in storage, an absolute local path, an
        ``http(s)`` URL, a ``File``, a PIL image, or a cropduster ``Image`` or
        field file. Other sources are copied to a new upload directory;
        Cropduster originals are reused in place.
    :param sizes: the sizes to crop. Defaults to the field's own, resolved
        against ``instance`` if they are declared as a callable.
    :param metadata: ``attribution``, ``attribution_link``, ``caption`` and
        ``alt_text`` for the image.
    :param crops: crop boxes by size name, for sizes that should not be framed
        by :func:`~cropduster.services.crops.choose_crop`. Each is a ``Box``, a
        ``Thumb``, a ``Crop`` or an ``(x, y, w, h)`` tuple, and is still fitted
        to the size it is given for.
    :param sources: reserved for per-crop source images. Naming any source but
        the one being attached raises ``NotImplementedError`` in 5.0.
    :param upload_to: overrides the field's, as a ``FileField``-style strftime
        pattern or callable.
    :param preview: write the preview rendition the crop dialog draws on.
    :param commit: save ``instance`` and attach its image and crops. With
        ``False``, crops for an unsaved instance remain unattached so the
        widget's formset can adopt them later.
    :param tmp: render the crops under their temporary names, to be promoted
        when the containing object is saved. Defaults to doing so exactly
        when ``instance`` has no pk.
    :param permissive: collect per-size failures in ``AttachResult.errors``
        instead of raising them. Sizes declared ``required=False`` are collected
        either way. This defaults to ``True``; :func:`copy_image` defaults to
        ``False`` because it generally has no editor to receive partial errors.
    :param skip_existing: keep crops that are already rendered and already have
        a row, rather than rendering them again.
    :raises ImageTooSmallError: the image is smaller than the required sizes.
    """
    return _attach(
        instance, field_name, source, sizes=sizes, metadata=metadata, crops=crops,
        sources=sources, upload_to=upload_to, preview=preview, commit=commit,
        tmp=tmp, permissive=permissive, skip_existing=skip_existing)


def copy_image(source, target_instance, field_name, *, metadata=None, crops=None,
               commit=True, tmp=None, reuse=None, permissive=False,
               skip_existing=False):
    """
    Attach an existing Cropduster image to another object's field.

    The original file is shared rather than copied: both images point at the
    same storage directory, and the source metadata is copied. Each target size
    uses the source crop with the greatest fitted overlap, preserving existing
    framing when the source and target declare different sizes.

    :param source: a cropduster ``Image``, or a cropduster field file (that is,
        ``some_object.some_field``).
    :param reuse: an ``Image`` row to write into rather than making one. ``True``
        means the row the target field already has, if it has one.
    :param permissive: defaults to ``False``, unlike :func:`attach`. A required
        size that cannot be rendered raises instead of returning an incomplete
        copy unless the caller requests partial results.

    Everything else is :func:`attach`'s.

    :raises CropDusterResizeException: a required size could not be cropped
        (unless ``permissive``).
    :raises ImageTooSmallError: the source is smaller than the target field's
        required sizes.
    :raises CropDusterFileMissing: the original is not in storage and could not
        be fetched back from the URL the storage reports for it.
    """
    source_image = _source_image(source)

    field = _resolve_field(target_instance, field_name)
    sizes = _resolve_sizes(target_instance, field, None)

    metadata = dict(_inherited_metadata(source_image), **(metadata or {}))
    crops = dict(_framing_from(source_image, sizes), **(crops or {}))

    return _attach(
        target_instance, field_name, source, sizes=sizes, metadata=metadata,
        crops=crops, sources=None, upload_to=None, preview=True, commit=commit,
        tmp=tmp, permissive=permissive, skip_existing=skip_existing,
        reuse=reuse)


def _attach(instance, field_name, source, *, sizes, metadata, crops, sources,
            upload_to, preview, commit, tmp, permissive, skip_existing,
            reuse=None):
    field = _resolve_field(instance, field_name)
    storage = get_image_storage()
    _check_sources(source, sources)

    if tmp is None:
        tmp = not instance.pk
    sizes = _resolve_sizes(instance, field, sizes)
    _check_crops(sizes, crops)
    _check_metadata(metadata)
    if upload_to is None:
        upload_to = field.file_field.upload_to

    previous_value = getattr(instance, field_name)
    files = _FileJournal(storage)
    assigned = False
    try:
        original = _store_original(
            source, sizes=sizes, upload_to=upload_to, preview=preview,
            storage=storage, files=files)

        image = _build_image(instance, field, original, metadata, reuse=reuse)
        rows = {thumb.name: thumb for thumb in image.thumbs.all()} if image.pk else {}
        result = AttachResult(
            image=image, warnings=list(original.warnings), sizes=sizes,
            preview=original.preview, tmp=tmp)
        _render_sizes(
            result, crops or {}, rows=rows, tmp=tmp, permissive=permissive,
            skip_existing=skip_existing, storage=storage, files=files)

        with transaction.atomic():
            if instance.pk:
                image.content_object = instance
                image.save()
            setattr(instance, field_name, image)
            assigned = True
            _save_rendered_thumbs(result)
            if commit:
                instance.save()
                _adopt(result, instance, field, files=files)
    except Exception:
        files.rollback()
        if assigned:
            setattr(instance, field_name, previous_value)
        raise
    else:
        files.close()
    return result


def _save_rendered_thumbs(result):
    """Save rendered rows after every required size has succeeded."""
    image = result.image
    for thumb in result.thumbs.values():
        thumb.image = image if (image.pk and not result.tmp) else None
        thumb.save()


def _adopt(result, instance, field, *, files=None):
    """
    Attach an image and the crops that were made under temporary names.

    Nothing could point at an instance while it had no pk, so its image was
    made unattached; crops are made unattached whenever they are rendered
    temporarily, whether or not there was an instance to attach them to. A
    thumb saved with its image set promotes its rendition to the name it is
    served under.
    """
    image = result.image
    if not instance.pk:
        return
    if not image.pk:
        image.content_object = instance
        image.save()
        setattr(instance, field.name, image)
    for thumb in result.thumbs.values():
        if result.tmp or thumb.image_id != image.pk:
            if result.tmp and files is not None:
                files.capture(image.get_image_path(thumb.name))
            thumb.image = image
            thumb.save()
    result.tmp = False


# ---------------------------------------------------------------------------
# The field, its sizes, and the row the image goes in
# ---------------------------------------------------------------------------

def _resolve_field(instance, field_name):
    field = get_cropduster_field(type(instance), name=field_name)
    if field is None:
        raise CropDusterConfigurationError(
            "%s has no CropDusterField named %r."
            % (type(instance).__name__, field_name))
    return field


def _resolve_sizes(instance, field, sizes):
    """
    The sizes to crop: the caller's, or the field's own.

    Read through the field file rather than off the field, because a field may
    declare its sizes as a callable of the instance they are being cropped for.
    Aliases are dropped: they name a rendition of another size rather than one
    of their own.
    """
    if sizes is None:
        sizes = getattr(instance, field.name).sizes
    return [
        size for size in normalize_sizes(sizes)
        if isinstance(size, Size) and not size.is_alias]


def _build_image(instance, field, original, metadata, reuse=None):
    image = _reused_image(instance, field, reuse)
    if image is None:
        # Supplying dimensions prevents the image field from reopening the
        # file while initializing its width and height.
        image = Image(
            field_identifier=field.field_identifier, image=original.name,
            width=original.width, height=original.height)
    else:
        if image.name != original.name:
            image.image = original.name
        image.width = original.width
        image.height = original.height

    for name, value in (metadata or {}).items():
        setattr(image, name, value)
    return image


def _reused_image(instance, field, reuse):
    """
    The ``Image`` row to write into, when the caller wants an existing one kept.

    Making a new row is the default, and when an attach replaces an image,
    ``Image.save`` orphans the replaced row. With ``reuse``, the row is kept,
    and with it its pk, its crops and anything pointing at them.
    """
    if reuse is None or reuse is False:
        return None
    if isinstance(reuse, Image):
        return reuse
    if not instance.pk:
        return None
    return Image.objects.filter(
        content_type=ContentType.objects.get_for_model(
            instance, for_concrete_model=field.for_concrete_model),
        object_id=instance.pk,
        field_identifier=field.field_identifier).first()


def _check_crops(sizes, crops):
    """
    Refuse a crop box drawn for a size that is not being cropped.

    Crop boxes are matched only by size name. Without validation, a misspelled
    name would be ignored and its framing lost. ``auto`` sizes are omitted
    because they use their parent size's box.
    """
    unknown = sorted(set(crops or ()) - {size.name for size in sizes})
    if unknown:
        raise ValueError(
            "No size named %s is being cropped; crops may name %s."
            % (', '.join(repr(name) for name in unknown),
               ', '.join(repr(size.name) for size in sizes) or "no size at all"))


def _check_metadata(metadata):
    unknown = sorted(set(metadata or ()) - set(METADATA_FIELDS))
    if unknown:
        raise TypeError(
            "%s is not image metadata; expected one of %s."
            % (', '.join(repr(name) for name in unknown),
               ', '.join(METADATA_FIELDS)))


def _check_sources(source, sources):
    """
    Refuse the per-crop source images the request format reserves.

    A ``sources`` mapping naming the image being attached for every size is the
    same request as not passing one at all, and is accepted so that a caller can
    build the mapping unconditionally.
    """
    if sources is None:
        return
    for name, value in dict(sources).items():
        if value is source or value == source:
            continue
        raise NotImplementedError(
            "Cropping %r from a source other than the image being attached is "
            "not implemented." % (name,))


# ---------------------------------------------------------------------------
# Storing the original
# ---------------------------------------------------------------------------

@dataclass
class _Original:
    """The stored original every crop is made from."""

    name: str
    width: int
    height: int
    preview: PreviewInfo | None = None
    warnings: list = field(default_factory=list)


class _FileJournal:
    """Restore or remove files when attachment does not complete."""

    def __init__(self, storage):
        self.storage = storage
        self.created = set()
        self.backups = {}

    def capture(self, path):
        if not path or path in self.created or path in self.backups:
            return
        if not self.storage.exists(path):
            self.created.add(path)
            return
        backup = SpooledTemporaryFile(max_size=1024 * 1024)
        with self.storage.open(path, 'rb') as stored:
            for chunk in iter(lambda: stored.read(64 * 1024), b''):
                backup.write(chunk)
        backup.seek(0)
        self.backups[path] = backup

    def mark_created(self, path):
        if path:
            self.created.add(path)

    def rollback(self):
        for path in self.created:
            self.storage.delete(path)
        for path, backup in self.backups.items():
            backup.seek(0)
            with self.storage.open(path, 'wb') as stored:
                for chunk in iter(lambda: backup.read(64 * 1024), b''):
                    stored.write(chunk)
        self.close()

    def close(self):
        for backup in self.backups.values():
            backup.close()
        self.backups.clear()
        self.created.clear()


def _store_original(source, *, sizes, upload_to, preview, storage, files):
    adopted = _adopted_original(source, upload_to=upload_to, storage=storage)
    if adopted is None:
        with _as_file(source, storage) as source_file:
            result = store_upload(
                source_file, upload_to=upload_to, sizes=sizes, preview=preview)
        files.mark_created(result.original_name)
        if result.preview is not None:
            files.mark_created(result.image.get_image_path('_preview'))
        return _Original(
            name=result.original_name, width=result.width, height=result.height,
            preview=result.preview, warnings=result.warnings)

    name, dimensions = adopted
    width, height = dimensions or _stored_dimensions(name, storage)
    min_w, min_h = get_min_size(sizes)
    if width < min_w or height < min_h:
        raise ImageTooSmallError((min_w, min_h), (width, height))

    return _Original(
        name=name, width=width, height=height,
        preview=(
            _preview_for(name, (width, height), storage, files)
            if preview else None))


def _adopted_original(source, *, upload_to, storage):
    """
    ``(name, dimensions)`` for a source already stored as a cropduster original.

    Cropduster keeps an original in a directory of its own, with its preview
    and its crops as siblings, so an image that is already one can be
    referenced rather than copied. Anything else is copied into a directory of
    its own, because writing crops next to it would mean writing them into
    another upload's directory. Dimensions are returned only when the source
    stores them, so no file is read here.
    """
    if isinstance(source, str) and URL_RE.search(source):
        downloaded = ImageFile(source, upload_to=upload_to)
        if not downloaded.name:
            raise CropDusterFileMissing("Could not download %s." % source)
        return (downloaded.name, None)

    if isinstance(source, Image):
        name, dimensions = source.name, (source.width, source.height)
    elif isinstance(source, VirtualFieldFile) or _is_cropduster_field_file(source):
        related = getattr(source, 'related_object', None)
        name = source.name
        dimensions = (related.width, related.height) if related is not None else None
    else:
        return None

    if not name:
        raise CropDusterFileMissing("%r holds no image." % (source,))
    if dimensions and None in dimensions:
        dimensions = None
    return (_recovered_original(source, name, upload_to, storage), dimensions)


def _is_cropduster_field_file(source):
    from cropduster.fields import CropDusterImageFieldFile

    return isinstance(source, CropDusterImageFieldFile)


def _recovered_original(source, name, upload_to, storage):
    """
    Return ``name`` after checking that the file exists to crop from.

    An ``Image`` row can outlive its file: the media moved to a CDN, or the
    database was restored from a dump taken without the media behind it. When
    the URL the source reports for itself is fetchable, the file is
    downloaded back into a directory of its own, and the copy proceeds.
    """
    if storage.exists(name):
        return name

    url = getattr(source, 'url', None)
    if url and URL_RE.search(url):
        try:
            recovered = ImageFile(url, upload_to=upload_to)
        except (SuspiciousOperation, URLError):
            # Downloading is disabled or the URL could not be fetched. The
            # original is missing either way, and the error below reports that.
            recovered = None
        if recovered is not None and recovered.name:
            return recovered.name
    else:
        url = None

    raise CropDusterFileMissing(
        "The original %s is not in storage%s."
        % (name, (" and could not be fetched from %s" % url) if url else ""))


@contextlib.contextmanager
def _as_file(source, storage):
    """
    ``source`` as a file to be stored, named after what it came from.

    Only the files opened here are closed here; a file passed in remains the
    caller's to close.
    """
    if isinstance(source, PIL.Image.Image):
        yield _pil_file(source)
        return
    if isinstance(source, File):
        yield File(source, name=os.path.basename(source.name or 'image'))
        return
    if not isinstance(source, str):
        raise TypeError(
            "Cannot attach %r. Pass a path, a URL, a File, a PIL image, or a "
            "cropduster Image." % (source,))

    path = source
    if settings.MEDIA_URL and path.startswith(settings.MEDIA_URL):
        path = get_relative_media_url(path, clean_slashes=False)
    if os.path.isabs(path) and os.path.exists(path):
        opened = open(path, 'rb')
    elif storage.exists(path):
        opened = storage.open(path, 'rb')
    else:
        raise CropDusterFileMissing("There is no image at %s." % source)

    try:
        yield File(opened, name=os.path.basename(path))
    finally:
        opened.close()


def _pil_file(pil_image):
    """
    A PIL image as a file, keeping the format it was decoded from.

    An image built in memory has no format at all, and is written as a PNG:
    lossless, so no detail is lost before the crops are made from it.
    """
    image_format = pil_image.format or 'PNG'
    extension = get_image_extension(pil_image) if pil_image.format else '.png'
    name = os.path.basename(getattr(pil_image, 'filename', '') or '')
    buf = BytesIO()
    pil_image.save(buf, format=image_format)
    return ContentFile(buf.getvalue(), name=name or 'image%s' % extension)


def _stored_dimensions(name, storage):
    with storage.open(name, mode='rb') as f:
        with PIL.Image.open(f) as pil_image:
            return pil_image.size


def _preview_for(name, dimensions, storage, files):
    """
    The preview rendition of an adopted original, written if it is missing.

    A stored Cropduster original normally has one. Storage is checked first
    so the image file is not opened during a copy when the preview already
    exists.
    """
    image = Image(image=name, width=dimensions[0], height=dimensions[1])
    path = image.get_image_path('_preview')
    if storage.exists(path):
        width, height = preview_dimensions(dimensions, preview_bounds())
        return PreviewInfo(width=width, height=height)
    files.capture(path)
    return _write_preview(
        image, open_stored_image(name, storage=storage), None,
        storage=storage)


# ---------------------------------------------------------------------------
# Rendering the sizes
# ---------------------------------------------------------------------------

def _render_sizes(result, crops, *, rows, tmp, permissive, skip_existing,
                  storage, files):
    """
    Crop every size, collecting what each one produced or why it could not be.

    A size is cropped before its ``auto`` children, which follow the box it
    was given; when a size fails, its children are skipped too.
    """
    image = result.image
    framing = _framing(image, result.sizes, crops, rows)
    source = (
        (image.width, image.height)
        if not cropduster_settings.CROPDUSTER_CREATE_THUMBS
        else _SourceOpener(image)(None))
    render = dict(
        tmp=tmp, permissive=permissive, skip_existing=skip_existing,
        storage=storage, files=files)

    for size in result.sizes:
        thumb = _render_size(
            result, size, source, row=rows.get(size.name),
            hint=framing[size.name], **render)
        if thumb is None:
            continue
        for auto_size in size.auto or []:
            _render_size(
                result, auto_size, source, row=rows.get(auto_size.name),
                reference=thumb, **render)


def _framing(image, sizes, crops, rows):
    """
    The crop each size is to be fitted to, decided before anything is rendered.

    Resolve all framing before rendering so size declaration order does not
    affect the result. Each size uses the boxes present when attachment began,
    not boxes created by an earlier size. A size without a box uses the complete
    image, matching the dialog.

    None means the size already has a box and is to keep it exactly. A box an
    editor drew need only be *within* the size's aspect band, so Cropduster
    does not re-fit it; a row with no box at all is framed like any other
    uncropped size.
    """
    dimensions = (image.width, image.height)
    hints = {
        name: as_crop(value, dimensions, image=image)
        for name, value in crops.items()}
    candidates = [row for row in rows.values() if not row.reference_thumb_id]
    frame = Crop(Box(0, 0, image.width, image.height), dimensions)

    framing = {}
    for size in sizes:
        if size.name in hints:
            framing[size.name] = hints[size.name]
        elif _has_box(rows.get(size.name)):
            framing[size.name] = None
        else:
            framing[size.name] = choose_crop(
                image, size, candidates=candidates, image_size=dimensions) or frame
    return framing


def _has_box(row):
    return row is not None and row.get_crop_box() is not None


def _render_size(result, size, source, *, row=None, hint=None, reference=None,
                 tmp, permissive, skip_existing, storage, files):
    image = result.image

    if row is not None and skip_existing and storage.exists(image.get_image_path(size.name)):
        if tmp:
            files.capture(image.get_image_path(size.name, tmp=True))
            _copy_to_tmp(image, size.name)
        result.thumbs[size.name] = row
        return row

    try:
        thumb = row
        if reference is None and hint is not None:
            # An auto size has no box of its own, and a size that already has
            # one keeps it (see _framing).
            computed = thumb_for_size(image, size, best_crop=hint)
            if computed is None:
                raise CropDusterResizeException(
                    "Image (%sx%s) is too small for size %s"
                    % (image.width, image.height, size.name))
            thumb = _with_geometry(row, computed)
        files.capture(image.get_image_path(size.name, tmp=tmp))
        thumb = image._save_thumb(
            size, image=source, thumb=thumb, ref_thumb=reference, tmp=tmp,
            commit=False)
    except CropDusterResizeException as e:
        result.errors[size.name] = e
        if size.required and not permissive:
            raise
        return None

    result.thumbs[size.name] = thumb
    return thumb


def _with_geometry(row, computed):
    if row is None:
        return computed
    for attname in GEOMETRY_FIELDS:
        setattr(row, attname, getattr(computed, attname))
    return row


# ---------------------------------------------------------------------------
# Copying
# ---------------------------------------------------------------------------

def _source_image(source):
    image = source if isinstance(source, Image) else getattr(source, 'related_object', None)
    if not isinstance(image, Image):
        raise CropDusterConfigurationError(
            "%r is not a cropduster image; copy_image() needs an Image, or a "
            "cropduster field file with one behind it, to copy the crops and "
            "metadata of." % (source,))
    return image


def _inherited_metadata(image):
    return {name: getattr(image, name) for name in METADATA_FIELDS}


def _framing_from(source_image, sizes):
    """
    The crop each of ``sizes`` is best taken from, among the source's own.

    The choice is made against the source image, because its rows hold the
    editor's boxes; the copy points at the same original, so a box means the
    same thing for both images.
    """
    dimensions = resolve_image_size(source_image)
    candidates = list(
        source_image.thumbs
        .filter(reference_thumb__isnull=True)
        .order_by('pk'))
    framing = {}
    for size in sizes:
        crop = choose_crop(
            source_image, size, candidates=candidates,
            image_size=dimensions)
        if crop is not None:
            framing[size.name] = crop
    return framing


# ---------------------------------------------------------------------------
# The legacy payload
# ---------------------------------------------------------------------------

def _legacy_payload(payload, *, sanitize=False):
    """
    The canonical payload as ``CropDuster.complete()`` reads it.

    The widget reads the crop form it would have submitted, answered with the
    crops that were made; the top-level ``thumbs`` is vestigial, read for its
    presence and nothing else.

    The metadata is at the top level rather than under a key of its own, and
    the preview is the first crop rather than the preview rendition, because
    this is the dict passed to a view's ``{"image": ...}``: the pages that
    fill a widget in from the server read the attribution and the alt text
    directly from it, and draw their preview with the crop the editor will
    see.
    """
    image = payload['image']
    crop = {
        'image_id': image['id'] or '',
        'orig_image': image['name'] or '',
        'orig_w': image['width'],
        'orig_h': image['height'],
        'thumbs': {
            name: {key: thumb[key] for key in ('id', 'name', 'width', 'height', 'url')}
            for name, thumb in payload['thumbs'].items()},
    }
    data = legacy_crop_response(image['name'], crop, sanitize=sanitize)
    data.update(payload['metadata'])
    data.update(_legacy_preview(data['crop']['thumbs']))
    return data


def _legacy_preview(thumbs):
    """The first crop, which is what the widget draws its preview with."""
    first = next(iter(thumbs.values()), None)
    if first is None:
        return {'preview_url': '', 'preview_w': None, 'preview_h': None}
    return {
        'preview_url': first['url'],
        'preview_w': first['width'],
        'preview_h': first['height'],
    }
