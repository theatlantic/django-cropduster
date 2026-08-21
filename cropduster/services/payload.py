"""Build the v1 payload and convert it to the 4.x response formats.

:func:`build_payload` uses the same versioned structure for the crop dialog,
upload responses, and programmatic attachment. ``image`` and ``thumbs`` are
separate top-level values. The format also reserves a ``source`` key on each
crop for a future request that uses an image other than ``image``.

:func:`payload_to_legacy` produces the existing 4.x upload and crop responses.
Downstream rich-text clients construct these requests themselves and read
individual response fields, so the adapter preserves their keys, values, and
stored-file URLs even when the configured renderer returns another URL.
"""

from collections.abc import Mapping

from cropduster.models import Image, Thumb, prime_reference_thumbs
from cropduster.renderers import get_renderer
from cropduster.resizing import Size
from cropduster.services.crop import CropResult
from cropduster.services.upload import (
    PreviewInfo, preview_bounds, preview_dimensions)
from cropduster.utils import json
from cropduster.utils.sizes import sanitize_size_name


__all__ = (
    'PAYLOAD_VERSION', 'build_payload', 'payload_to_legacy',
    'legacy_crop_response')


#: Incremented when an existing payload key changes meaning, but not when a
#: new key is added.
PAYLOAD_VERSION = 1

#: The fields the legacy wire reports for a crop inside a ``thumbs`` dict.
LEGACY_THUMB_FIELDS = ('id', 'name', 'width', 'height')


def build_payload(image, *, thumbs=None, sizes=None, preview=None, renderer=None,
                  tmp=False, warnings=()):
    """Describe ``image`` and its crops in the v1 payload format.

    :param thumbs: a :class:`~cropduster.services.crop.CropResult`, a mapping
        of thumbs, or an iterable of thumbs. When omitted, saved thumbs are
        read from ``image``. An unsaved image has no related rows and returns
        none. With a prefetched collection, the relation is not read again.
    :param sizes: the declared size set to serialize in the payload.
    :param preview: the known preview dimensions and URL. When omitted, they
        are calculated from the image.
    :param renderer: the URL backend. Defaults to ``CROPDUSTER_URL_RENDERER``.
    :param tmp: use temporary filenames for crops not yet saved with the image.
        A :class:`~cropduster.services.crop.CropResult` records this separately
        for each crop and ignores the shared value.
    :param warnings: ``{"code", "message"}`` dicts, or bare messages.
    """
    renderer = renderer or get_renderer()
    thumb_list, changed, suggestions, tmp_names = _resolve_thumbs(image, thumbs)
    by_pk = {thumb.pk: thumb for thumb in thumb_list if thumb.pk}

    payload_thumbs = {}
    for thumb in thumb_list:
        payload_thumbs[thumb.name] = _thumb_entry(
            thumb, image=image, renderer=renderer, thumbs=thumb_list, by_pk=by_pk,
            tmp=_is_tmp(thumb, tmp, tmp_names), changed=thumb.name in changed)
    for name, box in suggestions.items():
        payload_thumbs.setdefault(name, _suggestion_entry(name, box))

    return {
        'version': PAYLOAD_VERSION,
        'image': {
            'id': image.pk,
            'name': image.name,
            'url': renderer.original_url(image) if image.name else None,
            'width': image.width,
            'height': image.height,
            'field_identifier': image.field_identifier,
            'content_type_id': image.content_type_id,
            'object_id': image.object_id,
        },
        'preview': _preview_entry(image, preview, renderer),
        'sizes': [_serialize_size(size) for size in (sizes or [])],
        'thumbs': payload_thumbs,
        'metadata': {
            'attribution': image.attribution,
            'attribution_link': image.attribution_link,
            'caption': image.caption,
            'alt_text': image.alt_text,
        },
        'warnings': [_warning_entry(warning) for warning in warnings],
    }


def payload_to_legacy(payload, *, sanitize=False, crop=None, echo=None, result=None):
    """Convert a v1 payload to a 4.x upload or crop response.

    Omitting ``crop`` returns an upload response. For a crop response, ``crop``
    contains the submitted crop form, ``echo`` contains the submitted data for
    each size, and ``result`` maps those requests to their rendered thumbs.
    That positional mapping is required because standalone crops are renamed
    from their contents and no longer share the requested size name.

    ``sanitize=True`` runs crop names through
    :func:`~cropduster.utils.sizes.sanitize_size_name`, for consumers that
    subscript the ``thumbs`` dicts from a template.

    URLs in the 4.x response refer to stored files rather than renderer output
    because existing clients construct filenames from them.

    A crop response uses only the image name from the v1 payload. Callers that
    only need that response can pass the name directly to
    :func:`legacy_crop_response` without calling :func:`build_payload`.
    """
    if crop is None:
        return _legacy_upload(payload, sanitize=sanitize)
    return legacy_crop_response(
        payload['image']['name'], crop, echo=echo, result=result,
        sanitize=sanitize)


# ---------------------------------------------------------------------------
# v1 payload
# ---------------------------------------------------------------------------

def _resolve_thumbs(image, thumbs):
    """Normalize accepted ``thumbs`` values.

    Return ``(list, changed, suggestions, tmp_names)``. Only a
    :class:`~cropduster.services.crop.CropResult` supplies ``tmp_names`` because
    it records where each rendered file was written.
    """
    if thumbs is None:
        if not getattr(image, 'pk', None):
            return [], set(), {}, None
        loaded = list(image.thumbs.all())
        prime_reference_thumbs(loaded)
        return loaded, set(), {}, None
    if isinstance(thumbs, CropResult):
        return (
            list(thumbs.thumbs.values()), set(thumbs.changed),
            dict(thumbs.suggestions), set(thumbs.tmp_names))
    if isinstance(thumbs, Mapping):
        return list(thumbs.values()), set(), {}, None
    return list(thumbs), set(), {}, None


def _is_tmp(thumb, tmp, tmp_names):
    """Return whether a crop uses its temporary filename.

    Re-cropping clones a saved row before writing a temporary file, so the row
    alone cannot identify the filename. ``CropResult.tmp_names`` records that
    case. Callers without a ``CropResult`` use ``tmp`` for unsaved thumbs.
    """
    if tmp_names is not None:
        return thumb.name in tmp_names
    return bool(tmp) and not thumb.image_id


def _thumb_entry(thumb, *, image, renderer, thumbs, by_pk, tmp, changed):
    return {
        'id': thumb.pk,
        'name': thumb.name,
        'width': thumb.width,
        'height': thumb.height,
        'crop': _crop_box(thumb),
        'ref': _reference_name(thumb, by_pk),
        'ref_id': thumb.reference_thumb_id,
        'url': renderer.url(thumb, image=image, thumbs=thumbs, tmp=tmp),
        'srcset': renderer.srcset(thumb, image=image, thumbs=thumbs, tmp=tmp),
        # Existing clients construct filenames from the stored rendition URL,
        # while ``url`` may come from another renderer. Unsaved crops use
        # their temporary filenames in both values.
        'file_url': _file_url(
            image.name, thumb.name, tmp=tmp or not image.pk) or None,
        'tmp': tmp,
        'changed': changed,
        'source': None,
    }


def _suggestion_entry(name, box):
    """Return a payload entry for a suggested, unrendered crop."""
    return {
        'id': None,
        'name': name,
        'width': None,
        'height': None,
        'crop': {'x': box.x1, 'y': box.y1, 'width': box.w, 'height': box.h},
        'ref': None,
        'ref_id': None,
        'url': None,
        'srcset': None,
        'file_url': None,
        'tmp': False,
        'changed': True,
        'source': None,
    }


def _crop_box(thumb):
    """Return the thumb's crop box, or ``None`` when it follows ``ref``."""
    box = (thumb.crop_x, thumb.crop_y, thumb.crop_w, thumb.crop_h)
    if any(value is None for value in box):
        return None
    x, y, w, h = box
    return {'x': x, 'y': y, 'width': w, 'height': h}


def _reference_name(thumb, by_pk):
    if not thumb.reference_thumb_id:
        return None
    reference = by_pk.get(thumb.reference_thumb_id)
    if reference is None:
        # Use a cached relation when available, but do not add one query for
        # every automatic crop merely to include its reference name.
        reference = Thumb._meta.get_field('reference_thumb').get_cached_value(
            thumb, default=None)
    return getattr(reference, 'name', None)


def _preview_entry(image, preview, renderer):
    if preview is None:
        width, height = preview_dimensions(
            (image.width, image.height), preview_bounds())
        preview = PreviewInfo(width=width, height=height)
    if isinstance(preview, Mapping):
        entry = dict(preview)
    else:
        entry = {'width': preview.width, 'height': preview.height}
    entry['url'] = (
        renderer.preview_url(
            image, width=entry.get('width'), height=entry.get('height'))
        if image.name else None)
    # The widget and legacy responses use the stored preview URL, while the v1
    # ``url`` may come from another renderer.
    entry.setdefault('file_url', _file_url(image.name, 'preview') or None)
    entry.setdefault(
        'srcset',
        renderer.preview_srcset(
            image, width=entry.get('width'), height=entry.get('height'))
        if image.name else None)
    return entry


def _serialize_size(size):
    return size.__serialize__() if isinstance(size, Size) else size


def _warning_entry(warning):
    if isinstance(warning, Mapping):
        return dict(warning)
    return {'code': None, 'message': str(warning)}


# ---------------------------------------------------------------------------
# Legacy wire format
# ---------------------------------------------------------------------------

def _legacy_upload(payload, *, sanitize=False):
    """Build the 4.x upload response.

    A standalone response also includes the size assigned to the crop and its
    full-image crop box. These values remain JSON strings because the client
    copies them into form fields for the crop request.
    """
    image = payload['image']
    name = image['name']

    data = {'warning': [warning['message'] for warning in payload['warnings']]}
    data.update({
        'crop': {
            'orig_image': name,
            'orig_w': image['width'],
            'orig_h': image['height'],
            'image_id': image['id'],
        },
        'url': _file_url(name, 'preview'),
        'orig_image': name,
        'orig_w': image['width'],
        'orig_h': image['height'],
        'width': image['width'],
        'height': image['height'],
    })

    if not payload['thumbs']:
        return data

    thumb_name, thumb = next(iter(payload['thumbs'].items()))
    box = thumb['crop'] or {}
    data['thumbs'] = [{
        'crop_x': box.get('x'),
        'crop_y': box.get('y'),
        'crop_w': box.get('width'),
        'crop_h': box.get('height'),
        'width': thumb['width'],
        'height': thumb['height'],
        # The initial crop remains unsaved until the client accepts it. The
        # legacy response therefore omits its primary key.
        'id': None,
        'changed': True,
        'size': json.dumps(payload['sizes'][0] if payload['sizes'] else None),
        'name': thumb_name,
    }]
    data['crop'].update({
        'image_id': image['id'],
        'sizes': json.dumps(payload['sizes']),
    })
    return data


def legacy_crop_response(image_name, crop, *, echo=None, result=None,
                         sanitize=False):
    """Add rendered crop values to the submitted 4.x form data.

    The client copies the response back into its form fields. Each entry keeps
    its submitted structure and adds the values produced while rendering.
    ``image_name`` supplies the stored-file URL for each rendition.

    See :func:`payload_to_legacy` for what ``crop``, ``echo`` and ``result``
    are.
    """
    echo = echo or []
    crop_thumbs = crop.get('thumbs') or {}

    for entry, outcome in zip(echo, result.outcomes if result else []):
        if outcome.created:
            thumb = outcome.thumb
            for prop in ('crop_x', 'crop_y', 'crop_w', 'crop_h', 'width', 'height',
                         'id', 'name'):
                entry[prop] = getattr(thumb, prop)
            entry.update({'changed': True, 'url': _file_url(image_name, thumb.name)})

            entry_thumbs = entry.setdefault('thumbs', {})
            for created_name, created in outcome.created.items():
                created_data = _legacy_thumb(image_name, created)
                crop_thumbs[_size_name(created_name, sanitize)] = created_data
                if created.reference_thumb_id:
                    # An automatic crop belongs to its parent size, which is
                    # already represented by this entry.
                    continue
                entry_thumbs[_size_name(created_name, sanitize)] = created_data
        elif outcome.suggestion is not None:
            box = outcome.suggestion
            entry.update({
                'crop_x': box.x1,
                'crop_y': box.y1,
                'crop_w': box.w,
                'crop_h': box.h,
                'changed': True,
                'id': None,
            })

    for entry in echo:
        # The formset converts a submitted primary key to its Thumb instance.
        if isinstance(entry.get('id'), Thumb):
            entry['id'] = entry['id'].pk
        if sanitize and isinstance(entry.get('thumbs'), Mapping):
            entry['thumbs'] = _sanitize_keys(entry['thumbs'])

    crop['thumbs'] = _sanitize_keys(crop_thumbs) if sanitize else crop_thumbs

    preview_w, preview_h = _legacy_preview_size(crop)
    return {
        'crop': crop,
        'thumbs': echo,
        'initial': True,
        'preview_url': _file_url(image_name, 'preview'),
        'preview_w': preview_w,
        'preview_h': preview_h,
    }


def _legacy_thumb(image_name, thumb):
    data = {field: getattr(thumb, field) for field in LEGACY_THUMB_FIELDS}
    data['url'] = _file_url(image_name, thumb.name, tmp=not thumb.image_id)
    return data


def _legacy_preview_size(crop):
    """Return the preview dimensions reported by the 4.x crop response.

    These are not the dimensions of the preview file. An image that fits inside
    the preview box is reported at the box's size rather than its own, and the
    global default is used even when the dialog received another
    ``preview_size``. Clients must not use these values to scale crop boxes:
    4.x measured ``#cropbox`` after rendering, and 5.0 measures the rendered
    ``<img>``. The response retains the values for compatibility.
    """
    bounds = preview_bounds()
    width, height = crop.get('orig_w'), crop.get('orig_h')
    if not width or not height:
        return bounds
    if min(bounds[0] / width, bounds[1] / height) >= 1:
        return bounds
    return preview_dimensions((width, height), bounds)


def _file_url(image_name, size_name, tmp=False):
    """Return a stored rendition URL without calling the renderer."""
    if not image_name:
        return ''
    image_file = Image.get_file_for_size(image_name, size_name, tmp=tmp)
    return getattr(image_file, 'url', None) or ''


def _size_name(name, sanitize):
    return sanitize_size_name(name) if sanitize else name


def _sanitize_keys(thumbs):
    return {sanitize_size_name(name): value for name, value in thumbs.items()}
