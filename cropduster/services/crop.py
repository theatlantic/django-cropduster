"""Apply crop boxes to an image.

:func:`apply_crops` accepts one :class:`ThumbRequest` per size. A changed crop
is rendered under a new ``Thumb`` row. An unchanged crop is copied to the
temporary filename read by the dialog. A size without crop coordinates
receives a suggested box instead of a file. A single call may contain any
combination of these requests.

``ThumbRequest.source`` identifies the image from which a crop is taken. In
5.0 it may only name the image being cropped; another value raises
``NotImplementedError``. Per-crop source overrides, which the request
format reserves, would need additional sources in :class:`_SourceOpener`.
"""

from dataclasses import dataclass, field

from cropduster.models import Image, Thumb
from cropduster.resizing import Box, Size
from cropduster.services.upload import open_stored_image


__all__ = ('ThumbRequest', 'ThumbOutcome', 'CropResult', 'apply_crops')


class _Unset:
    """Mark a request field that the caller did not supply."""


UNSET = _Unset()


@dataclass
class ThumbRequest:
    """Describe the requested state of one size.

    :param crop: the box in source pixels, or ``None`` for a size that has not
        been cropped.
    :param changed: the box differs from the one the thumb was rendered with,
        so the rendition must be recreated under a new row. A box without a
        ``thumb_id`` is a new crop and is also considered changed.
    :param source: the name of the source image. ``None`` selects the image
        being cropped, which is the only source supported in 5.0.
    :param thumb: a row already loaded by the caller. When omitted,
        ``thumb_id`` is used to load it.
    """

    name: str
    size: Size
    thumb_id: int | None = None
    crop: Box | None | _Unset = UNSET
    width: int | None | _Unset = UNSET
    height: int | None | _Unset = UNSET
    changed: bool = False
    source: str | None = None
    thumb: Thumb | None = None


@dataclass
class ThumbOutcome:
    """Describe the result of one :class:`ThumbRequest`."""

    request: ThumbRequest
    #: The resulting thumb, whether or not a rendition was created.
    thumb: Thumb | None = None
    #: Thumbs rendered for this request, including its ``auto`` sizes.
    created: dict = field(default_factory=dict)
    #: Whether the saved rendition was copied to its temporary filename.
    copied: bool = False
    #: Whether the result refers to a temporary rendition that differs from
    #: the saved file.
    tmp: bool = False
    #: Suggested box for a size that has not been cropped.
    suggestion: Box | None = None

    @property
    def changed(self):
        return bool(self.created)


@dataclass
class CropResult:
    """Describe an image's crops after :func:`apply_crops`."""

    image: Image
    #: Thumbs used or created by this call, including ``auto`` sizes.
    thumbs: dict = field(default_factory=dict)
    #: Suggested boxes for uncropped sizes, keyed by size name.
    suggestions: dict = field(default_factory=dict)
    #: Names of thumbs rendered by this call.
    changed: set = field(default_factory=set)
    #: Names whose current rendition uses a temporary filename. A recreated
    #: crop retains its saved row, so this cannot be inferred from the row.
    tmp_names: set = field(default_factory=set)
    #: Results in the same order as the requests.
    outcomes: list = field(default_factory=list)


def apply_crops(image, requests, *, standalone=False, tmp=True, pil_image=None):
    """Apply each request to ``image``.

    :param tmp: render to temporary filenames read by the crop UI, leaving
        saved renditions unchanged until the containing object is saved.
    :param pil_image: an already-open source image.

    ``CropDusterResizeException`` is not caught. The caller reports a crop box
    that is too small, and any earlier crops in the request have already been
    written to storage.
    """
    requests = list(requests)
    open_source = _SourceOpener(image, pil_image)

    thumbs = [_thumb_for_request(request) for request in requests]
    # Choose the first existing crop before rendering. Suggestions must use a
    # box supplied by the caller rather than one created during this call.
    cropped = [thumb for thumb in thumbs if thumb.crop_w and thumb.crop_h]

    result = CropResult(image=image)

    for request, thumb in zip(requests, thumbs):
        outcome = ThumbOutcome(request=request, thumb=thumb)
        result.outcomes.append(outcome)

        if request.changed:
            source = open_source(request.source)
            # A changed box creates a new row. The saved thumb remains until
            # the object containing the Cropduster field is saved.
            thumb.pk = None
            thumb.width = min(filter(None, [thumb.width, thumb.crop_w]))
            thumb.height = min(filter(None, [thumb.height, thumb.crop_h]))

            created = image.save_size(
                request.size, thumb, image=source, tmp=tmp, standalone=standalone)
            if not created:
                continue
            if standalone:
                # A standalone crop is named from its contents, and
                # save_size() returns a single Thumb for it rather than a
                # dictionary of named sizes.
                thumb = created
                created = {thumb.name: thumb}

            outcome.thumb = thumb = created.get(thumb.name, thumb)
            outcome.created = created
            outcome.tmp = bool(tmp and not standalone)
            result.thumbs.update(created)
            result.changed.update(created)
            if outcome.tmp:
                result.tmp_names.update(created)
        elif thumb.pk and thumb.name and thumb.crop_w and thumb.crop_h:
            tmp_is_current = bool(tmp) and _tmp_rendition_is_current(thumb)
            if tmp:
                outcome.copied = _copy_to_tmp(
                    image, thumb.name,
                    keep_existing_tmp=tmp_is_current)
            outcome.tmp = tmp_is_current and not outcome.copied
            result.thumbs.setdefault(thumb.name, thumb)
            if outcome.tmp:
                result.tmp_names.add(thumb.name)

        if not thumb.pk and not thumb.crop_w and not thumb.crop_h:
            if not cropped:
                continue
            source = open_source(request.source)
            if source is None:
                continue
            best_fit = request.size.fit_to_crop(cropped[0], original_image=source)
            if best_fit:
                outcome.suggestion = best_fit.box
                result.suggestions[request.name] = best_fit.box

    return result


def _thumb_for_request(request):
    """Apply request values to its stored or new ``Thumb`` row.

    The stored row supplies values omitted from the request, including its
    image and the reference thumb used by an ``auto`` size. A formset has
    already loaded the row while binding its form and can pass it through
    ``request.thumb``.
    """
    thumb = request.thumb
    if thumb is None and request.thumb_id:
        thumb = Thumb.objects.filter(pk=request.thumb_id).first()
    if thumb is None:
        thumb = Thumb()

    thumb.name = request.name
    if request.width is not UNSET:
        thumb.width = request.width
    if request.height is not UNSET:
        thumb.height = request.height
    if request.crop is not UNSET:
        box = request.crop
        thumb.crop_x = None if box is None else box.x1
        thumb.crop_y = None if box is None else box.y1
        thumb.crop_w = None if box is None else box.w
        thumb.crop_h = None if box is None else box.h
    return thumb


def _tmp_rendition_is_current(thumb):
    """Return whether this row owns its size's temporary rendition.

    A new crop can retain its image foreign key until the containing object is
    saved, so the foreign key alone does not distinguish a saved crop from a
    pending replacement. The pending replacement is the newest same-name row
    attached to an image that still has an older same-name row.
    """
    if not thumb.image_id:
        return True
    sibling_pks = list(
        Thumb.objects
        .filter(image_id=thumb.image_id, name=thumb.name)
        .exclude(pk=thumb.pk)
        .values_list('pk', flat=True))
    return bool(sibling_pks) and thumb.pk > max(sibling_pks)


def _copy_to_tmp(image, name, *, keep_existing_tmp=False):
    """Copy a saved rendition to the temporary filename used by the crop UI.

    When the form is saved, temporary renditions are promoted and the others
    removed, so even an unchanged size needs a temporary file. A temporary
    rendition already created during the current session is not replaced.
    """
    storage = image.storage
    saved_path = image.get_image_path(name, tmp=False)
    tmp_path = image.get_image_path(name, tmp=True)

    if not storage.exists(saved_path):
        return False
    if keep_existing_tmp and storage.exists(tmp_path):
        return False

    with storage.open(saved_path) as f:
        with storage.open(tmp_path, 'wb') as tmp_file:
            tmp_file.write(f.read())
    return True


class _SourceOpener:
    """Open each source image at most once per :func:`apply_crops` call.

    Multiple sizes normally use the same source, which is held as a complete
    image in memory.
    """

    def __init__(self, image, pil_image=None):
        self.image = image
        self.name = getattr(image, 'name', None)
        self._cache = {}
        if pil_image is not None:
            self._cache[self.name] = pil_image

    def __call__(self, spec):
        name = self.name if spec is None else spec
        if name != self.name:
            raise NotImplementedError(
                "Cropping from a source other than the image being cropped is "
                "not implemented; ThumbRequest.source must be None or %r, got "
                "%r." % (self.name, spec))
        if name not in self._cache:
            self._cache[name] = self._open()
        return self._cache[name]

    def _open(self):
        try:
            pil_image = open_stored_image(
                self.image.image.name, storage=self.image.storage)
        except IOError:
            # A suggestion needs only dimensions. Rendering still raises the
            # storage error when save_size() reopens the source.
            if self.image.width and self.image.height:
                return (self.image.width, self.image.height)
            return None
        return pil_image
