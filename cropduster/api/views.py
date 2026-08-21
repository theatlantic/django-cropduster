"""Implement the state, upload, and crop JSON endpoints.

All three return the v1 payload from
:func:`cropduster.services.payload.build_payload`. Each endpoint performs a
different operation before building the same response structure.

Storage operations are delegated to :mod:`cropduster.services`, which is also
used by the legacy endpoints. The APIs differ in request parsing and error
responses.
"""

import hashlib

from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.views.decorators.http import require_http_methods

from cropduster.api.errors import ApiError, json_api_view
from cropduster.api.permissions import check_permission
from cropduster.api.schema import (
    TargetInfo, crop_suggestions, effective_sizes, limit_size_widths, parse_bool,
    parse_crop_box, parse_int, parse_json, parse_preview_size, parse_sizes,
    parse_target, parse_thumb_ids, size_by_name)
from cropduster.conf import settings as cropduster_settings
from cropduster.exceptions import CropDusterConfigurationError
from cropduster.files import ImageFile, normalize_stored_image_name
from cropduster.models import Image, Thumb, prime_reference_thumbs
from cropduster.renderers import get_renderer
from cropduster.services.crop import CropResult, ThumbRequest, apply_crops
from cropduster.services.payload import build_payload
from cropduster.services.upload import (
    PreviewInfo, preview_bounds, preview_dimensions, store_upload)
from cropduster.standalone import require_standalone
from cropduster.utils.fields import get_cropduster_field


__all__ = ('crop', 'state', 'upload')


ORPHAN_THUMB_SESSION_KEY = 'cropduster.orphan_thumbs'


def api_view(*methods):
    """Apply method, CSRF, JSON-error, cache, and frame decorators.

    The method and CSRF token are checked before permissions or request input.
    :func:`~cropduster.api.errors.json_api_view` turns a payload, a raised
    error, or the HTML response from either inner decorator into JSON. The
    header decorators are outermost so they apply to error responses too.

    The outer ``csrf_exempt`` makes ``CsrfViewMiddleware`` defer to the inner
    ``csrf_protect`` decorator. This allows :func:`json_api_view` to convert a
    CSRF rejection to JSON instead of returning the project's HTML failure
    page.
    """
    def decorate(view):
        view = csrf_protect(view)
        view = require_http_methods(list(methods))(view)
        view = json_api_view(view)
        view = xframe_options_exempt(view)
        view = never_cache(view)
        return csrf_exempt(view)

    return decorate


@api_view("POST")
def state(request):
    """Return the image, sizes, thumbs, and preview needed by the dialog.

    The image is named either by ``image`` (a storage path, a MEDIA_URL-based
    path, or an off-site URL to be downloaded), by ``id``, or by both. When
    the two name different files, the editor has replaced the image, and the
    row is reported without its pk because a new image gets a new row.

    A size without a crop receives a box fitted from the first existing crop.
    The endpoint also writes a missing preview because the dialog uses that
    image for crop selection.
    """
    params = request.POST
    target = parse_target(params.get('target'))
    check_permission(request, target)

    preview_size = parse_preview_size(params.get('preview_size'))
    upload_to = (
        target.upload_to if target is not None
        else (params.get('upload_to') or None))

    image_id = params.get('id')
    _check_target_image(target, image_id)
    persisted_image = _db_image(image_id)
    if target is None and persisted_image is not None:
        inferred_target = _target_for_image(persisted_image)
        if inferred_target is not None:
            check_permission(request, inferred_target)

    requested_image = params.get('image')
    prechecked_name = normalize_stored_image_name(requested_image)
    if prechecked_name and prechecked_name.startswith('//'):
        raise ApiError(
            400, 'invalid',
            "image must be a storage path or an absolute HTTP(S) URL.",
            field='image')
    if prechecked_name is not None:
        _check_named_image_permissions(
            request, target, prechecked_name)

    image_file = ImageFile(
        requested_image, upload_to=upload_to,
        preview_w=preview_size[0], preview_h=preview_size[1])
    image = _state_image(persisted_image, image_file)
    if image.pk is None and image.name != prechecked_name:
        _check_named_image_permissions(request, target, image.name)

    sizes = effective_sizes(target, parse_sizes(params.get('sizes')))
    sizes = limit_size_widths(
        sizes, parse_int(params.get('max_w'), 'max_w'), image.width)

    thumbs = _state_thumbs(
        request, image, parse_thumb_ids(params.get('thumbs')))
    crops = CropResult(
        image=image,
        thumbs={thumb.name: thumb for thumb in thumbs},
        suggestions=crop_suggestions(image, sizes, thumbs))

    return _json(build_payload(
        image, thumbs=crops, sizes=sizes,
        preview=_preview(image, preview_size)))


@api_view("POST")
def upload(request):
    """Validate and store an upload, then return its v1 state.

    The upload is validated against the sizes it will have to satisfy before
    anything is written, so an image that is too small is refused with the
    dimensions it needed (``image_too_small``). ``for_size`` restricts the
    minimum to one size and its automatic children.
    """
    target = parse_target(request.POST.get('target'))
    check_permission(request, target)

    uploaded = request.FILES.get('image')
    if uploaded is None:
        raise ApiError(400, 'invalid', "No image was uploaded.", field='image')

    standalone = parse_bool(request.POST.get('standalone'))
    if standalone:
        _require_standalone()

    _check_md5(request.POST.get('md5'), uploaded)

    sizes = effective_sizes(target, parse_sizes(request.POST.get('sizes')))
    for_size = request.POST.get('for_size') or None
    if for_size is not None:
        size_by_name(sizes, for_size, field='for_size')

    preview_size = (
        parse_int(request.POST.get('preview_width'), 'preview_width'),
        parse_int(request.POST.get('preview_height'), 'preview_height'))

    result = store_upload(
        uploaded,
        upload_to=(
            target.upload_to if target is not None
            else (request.POST.get('upload_to') or None)),
        sizes=sizes,
        preview_size=preview_size,
        standalone=standalone,
        for_size=for_size)

    return _json(build_payload(
        result.image,
        thumbs=[result.standalone_thumb] if result.standalone_thumb else [],
        sizes=result.sizes,
        preview=result.preview,
        warnings=result.warnings))


@api_view("POST")
def crop(request):
    """Render requested crops and return their v1 state.

    The body is JSON: an ``image`` block naming what is being cropped, the
    ``sizes`` it is being cropped for, and a ``thumbs`` entry per size
    describing what should happen to it: a box that changed is rendered
    again, one that did not is left alone, and a size with no box at all is
    answered with a suggestion.

    Renditions use temporary filenames until the widget's form is saved. This
    endpoint does not save the containing object or attach the image to it.
    """
    data = parse_json(request.body, 'body') or {}
    if not isinstance(data, dict):
        raise ApiError(400, 'invalid', "The request body must be an object.")

    target = parse_target(data.get('target'))
    check_permission(request, target)

    standalone = parse_bool(data.get('standalone'))
    if standalone:
        _require_standalone()

    image_data = data.get('image') or {}
    if not isinstance(image_data, dict):
        raise ApiError(
            400, 'invalid', "image must be an object.", field='image')
    _check_target_image(target, image_data.get('id'))
    image = _crop_image(image_data)
    if image.pk is None:
        _check_named_image_permissions(request, target, image.name)
    elif target is None:
        inferred_target = _target_for_image(image)
        if inferred_target is not None:
            check_permission(request, inferred_target)
    sizes = effective_sizes(target, parse_sizes(data.get('sizes')))
    requests = _thumb_requests(
        request, image, sizes, data.get('thumbs') or {})

    result = apply_crops(image, requests, standalone=standalone, tmp=True)
    _bind_orphan_thumbs(request, image, result.thumbs.values())

    return _json(build_payload(image, thumbs=result, sizes=sizes, tmp=True))


# ---------------------------------------------------------------------------
# state
# ---------------------------------------------------------------------------

def _state_image(db_image, image_file):
    """Return the saved or replacement image opened by the dialog.

    A row whose stored filename differs from the one the request named is
    returned without its primary key because replacing an original creates a
    new row instead of overwriting the old crops. If the original is missing
    from storage, return an empty image so the dialog opens on the upload step.
    """
    if db_image is not None:
        name = getattr(image_file, 'name', None)
        if name and name != db_image.image.name:
            return _new_image(name)
        return db_image

    name = getattr(image_file.get_for_size('original'), 'name', None)
    return _new_image(name)


def _new_image(name):
    """Return an unsaved ``Image`` for ``name``, or an empty one on failure."""
    if not name:
        return Image()
    try:
        return Image(image=name)
    except (OSError, ValueError):
        return Image()


def _db_image(image_id):
    """Return the requested ``Image`` row, or ``None`` when it is absent."""
    if not image_id:
        return None
    try:
        return Image.objects.get(pk=image_id)
    except (TypeError, ValueError, Image.DoesNotExist):
        return None


def _state_thumbs(request, image, thumb_ids):
    """Return the thumbs used to initialize the dialog.

    Explicit primary keys select the rows bound to the current formset, which
    may differ from the saved relation while a form is being edited. Omitting
    the parameter reads the image's saved thumbs.
    """
    if thumb_ids:
        thumbs = [
            thumb for thumb in Thumb.objects.filter(pk__in=thumb_ids)
            if _thumb_belongs_to_image(request, thumb, image)]
    elif thumb_ids is None and image.pk:
        thumbs = list(image.thumbs.all())
    else:
        thumbs = []
    prime_reference_thumbs(thumbs)
    return thumbs


def _preview(image, preview_size):
    """Return the preview and create its file when missing.

    The dialog uses this image for crop selection, so state cannot report a
    preview before its file exists.
    """
    bounds = preview_bounds(preview_size)
    width, height = preview_dimensions((image.width, image.height), bounds)

    if not image.name:
        return PreviewInfo(width=width, height=height)

    renderer = get_renderer()
    if not image.storage.exists(image.get_image_path('_preview')):
        try:
            image.save_preview(preview_w=bounds[0], preview_h=bounds[1])
        except (OSError, ValueError) as error:
            if not renderer.supports_metadata_only:
                raise ApiError(
                    400, 'invalid_image',
                    "The preview for %s could not be created: %s"
                    % (image.name, error),
                    field='image')
        if (not renderer.supports_metadata_only
                and not image.storage.exists(image.get_image_path('_preview'))):
            raise ApiError(
                400, 'invalid_image',
                "The preview for %s could not be created." % image.name,
                field='image')

    return PreviewInfo(width=width, height=height)


# ---------------------------------------------------------------------------
# crop
# ---------------------------------------------------------------------------

def _crop_image(data):
    """Return the saved or unsaved image named by a crop request."""
    image_id = parse_int(data.get('id'), 'image')
    if image_id:
        return Image.objects.get(pk=image_id)

    name = data.get('name')
    if not name:
        raise ApiError(
            400, 'invalid', "The image must be named by id or by name.",
            field='image')

    width = parse_int(data.get('width'), 'image')
    height = parse_int(data.get('height'), 'image')
    try:
        # Supplying dimensions prevents the field from opening the original and
        # also permits a request to describe a missing file.
        return Image(image=name, width=width, height=height)
    except (OSError, ValueError):
        raise ApiError(
            400, 'invalid_image', "%s could not be read." % name, field='image')


def _thumb_requests(request, image, sizes, thumbs):
    """
    One :class:`~cropduster.services.crop.ThumbRequest` per size, in order.

    The order is the declared one rather than the order the request happens
    to list its crops in: an uncropped size takes its suggestion from the
    first cropped one, so the choice must be a property of the size set.
    """
    if not isinstance(thumbs, dict):
        raise ApiError(400, 'invalid', "thumbs must be an object.", field='thumbs')

    declared = {size.name for size in sizes}
    for name in thumbs:
        if name not in declared:
            raise ApiError(
                400, 'unknown_size', "No size named %r was declared." % (name,),
                field='thumbs')

    return [
        _thumb_request(request, image, size, thumbs[size.name])
        for size in sizes if size.name in thumbs]


def _thumb_request(request, image, size, entry):
    field = 'thumbs.%s' % size.name
    if not isinstance(entry, dict):
        raise ApiError(400, 'invalid', "%s must be an object." % field, field=field)

    source = entry.get('source')
    if source is not None and source != image.name:
        # The request format reserves per-crop sources, but 5.0 only supports
        # the image being cropped.
        raise ApiError(
            501, 'per_size_source_unsupported',
            "Cropping %r from a source other than the image being cropped is "
            "not implemented." % size.name,
            field=field, details={'source': source})

    thumb_id = parse_int(entry.get('id'), field)
    thumb = None
    if thumb_id is not None:
        thumb = Thumb.objects.filter(pk=thumb_id).first()
        if thumb is None:
            raise ApiError(
                404, 'not_found', "No crop with id %s exists." % thumb_id,
                field=field)
        if not _thumb_belongs_to_image(
                request, thumb, image, expected_name=size.name):
            raise ApiError(
                400, 'invalid',
                "%s does not belong to the image being cropped." % field,
                field=field)

    crop = parse_crop_box(entry.get('crop'), '%s.crop' % field)
    if (crop is not None and image.width and image.height
            and (crop.x2 > image.width or crop.y2 > image.height)):
        raise ApiError(
            400, 'invalid',
            "%s.crop extends beyond the image dimensions." % field,
            field='%s.crop' % field)
    changed = parse_bool(entry.get('changed'))
    if changed and crop is None:
        raise ApiError(
            400, 'invalid',
            "%s.crop is required when changed is true." % field,
            field='%s.crop' % field)

    return ThumbRequest(
        name=size.name,
        size=size,
        thumb_id=thumb_id,
        thumb=thumb,
        crop=crop,
        width=parse_int(entry.get('width'), field),
        height=parse_int(entry.get('height'), field),
        changed=changed,
        source=source)


# ---------------------------------------------------------------------------
# shared
# ---------------------------------------------------------------------------

def _check_target_image(target, image_id):
    """Reject a saved image that does not belong to the target field."""
    if target is None or image_id in (None, ''):
        return
    image_id = parse_int(image_id, 'image')
    related = target.related_image
    if related is None or related.pk != image_id:
        raise ApiError(
            400, 'target_mismatch',
            "The image does not belong to the target field.", field='image')


def _target_for_image(image):
    """Return the target field associated with a saved image, when available."""
    if not (
            image.pk and image.content_type_id and image.object_id is not None):
        return None
    model = image.content_type.model_class()
    if model is None:
        return None
    field = get_cropduster_field(
        model, field_identifier=image.field_identifier)
    if field is None:
        return None
    return TargetInfo(
        content_type=model._meta.label_lower,
        field_name=field.name,
        object_id=image.object_id)


def _check_named_image_permissions(request, target, name):
    """Check owners of a stored filename when no image ID was supplied."""
    if not name:
        return
    owners = list(Image.objects.filter(image=name).select_related('content_type'))
    if not owners:
        return
    if target is not None:
        related = target.related_image
        if related is None or related.name != name:
            raise ApiError(
                400, 'target_mismatch',
                "The image does not belong to the target field.",
                field='image')
        return
    for owner in owners:
        inferred_target = _target_for_image(owner)
        if inferred_target is not None:
            check_permission(request, inferred_target)


def _bind_orphan_thumbs(request, image, thumbs):
    """Bind newly created orphan rows to this session and image."""
    bindings = dict(request.session.get(ORPHAN_THUMB_SESSION_KEY, {}))
    changed = False
    for thumb in thumbs:
        if thumb.pk is None or thumb.image_id is not None:
            continue
        bindings[str(thumb.pk)] = [image.name, thumb.name]
        changed = True
    if changed:
        request.session[ORPHAN_THUMB_SESSION_KEY] = bindings


def _thumb_belongs_to_image(request, thumb, image, expected_name=None):
    if expected_name is not None and thumb.name != expected_name:
        return False
    if thumb.image_id is not None:
        return bool(image.pk and thumb.image_id == image.pk)
    if image.pk or not image.name or not thumb.name:
        return False
    bindings = request.session.get(ORPHAN_THUMB_SESSION_KEY, {})
    if bindings.get(str(thumb.pk)) != [image.name, thumb.name]:
        return False
    if not cropduster_settings.CROPDUSTER_CREATE_THUMBS:
        return True
    return image.storage.exists(image.get_image_path(thumb.name, tmp=True))

def _require_standalone():
    try:
        require_standalone()
    except CropDusterConfigurationError as e:
        raise ApiError(501, 'standalone_unavailable', str(e), field='standalone')


def _check_md5(claimed, uploaded):
    """Reject an upload whose MD5 does not match the submitted value."""
    if not claimed:
        return

    md5 = hashlib.md5()
    for chunk in uploaded.chunks():
        md5.update(chunk)
    uploaded.seek(0)

    actual = md5.hexdigest()
    if claimed != actual:
        raise ApiError(
            400, 'md5_mismatch',
            "The uploaded file does not hash to the md5 that was declared for "
            "it.", field='md5', details={'expected': claimed, 'actual': actual})


def _json(payload):
    return JsonResponse(payload)
