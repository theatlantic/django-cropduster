"""Parse JSON API fields and resolve their model target.

Request values arrive as strings or parsed JSON. Each parser returns the value
expected by the service layer or raises :class:`~cropduster.api.errors.ApiError`
with status 400 and the invalid field name.

``target`` contains ``content_type``, ``object_id``, and ``field_name``. When
present, the model field supplies the upload directory and size definitions;
client size names may only select from that set. Without a target, the API uses
the supplied values, matching the legacy behavior needed by unsaved objects.
"""

from django.apps import apps
from django.utils.functional import cached_property

from cropduster.api.errors import ApiError
from cropduster.resizing import Box, Size
from cropduster.utils import json
from cropduster.utils.fields import get_cropduster_field, get_image_column_field


__all__ = (
    'TargetInfo', 'crop_suggestions', 'effective_sizes', 'limit_size_widths',
    'parse_bool', 'parse_crop_box', 'parse_int', 'parse_json',
    'parse_preview_size', 'parse_sizes', 'parse_target', 'parse_thumb_ids',
    'size_by_name')


def parse_int(value, field, *, default=None):
    if value in (None, ''):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ApiError(
            400, 'invalid', "%r is not a whole number." % (value,), field=field)


def parse_bool(value):
    """Parse boolean values used by HTML forms and JSON bodies."""
    if isinstance(value, str):
        return value.strip().lower() in ('1', 'true', 'on', 'yes')
    return bool(value)


def parse_json(value, field):
    if value in (None, ''):
        return None
    if not isinstance(value, (str, bytes)):
        return value
    try:
        return json.loads(value)
    except ValueError:
        raise ApiError(400, 'invalid', "%s is not valid JSON." % field, field=field)


def parse_sizes(value, field='sizes'):
    """Parse a serialized list of :class:`~cropduster.resizing.Size` objects.

    The widget puts this JSON form in a form field and clients post it back;
    :mod:`cropduster.utils.jsonutils` reconstructs the ``Size`` instances
    rather than plain dicts.
    """
    sizes = parse_json(value, field)
    if sizes is None:
        return None
    if not isinstance(sizes, list):
        raise ApiError(400, 'invalid', "%s must be a list." % field, field=field)
    for size in sizes:
        if not isinstance(size, Size):
            raise ApiError(
                400, 'invalid', "%s must be a list of serialized sizes." % field,
                field=field)
    return sizes


def parse_preview_size(value, field='preview_size'):
    """Parse ``"WxH"`` with either dimension optionally omitted."""
    if not value:
        return (None, None)
    parts = str(value).split('x')
    if len(parts) != 2:
        raise ApiError(
            400, 'invalid', "%s must be given as WxH." % field, field=field)
    return (parse_int(parts[0], field), parse_int(parts[1], field))


def parse_thumb_ids(value, field='thumbs'):
    """Parse comma-separated crop primary keys, or return ``None``."""
    if value in (None, ''):
        return None
    return [parse_int(part, field) for part in str(value).split(',') if part]


def parse_crop_box(value, field):
    """Parse a crop box for the service layer."""
    if value in (None, {}):
        return None
    if not isinstance(value, dict):
        raise ApiError(400, 'invalid', "%s must be an object." % field, field=field)
    x = parse_int(value.get('x'), field)
    y = parse_int(value.get('y'), field)
    width = parse_int(value.get('width'), field)
    height = parse_int(value.get('height'), field)
    if None in (x, y, width, height):
        raise ApiError(
            400, 'invalid', "%s needs x, y, width and height." % field, field=field)
    if x < 0 or y < 0 or width <= 0 or height <= 0:
        raise ApiError(
            400, 'invalid',
            "%s needs non-negative x and y and positive width and height."
            % field, field=field)
    return Box(x, y, x + width, y + height)


class TargetInfo:
    """Resolve the model field named by a request target.

    Properties are resolved lazily so the permission check can reject an
    unauthenticated request before reading its model or field.
    """

    def __init__(self, content_type, field_name, object_id=None):
        self.content_type = content_type
        self.field_name = field_name
        self.object_id = object_id

    def __repr__(self):
        return "<TargetInfo %s.%s pk=%r>" % (
            self.content_type, self.field_name, self.object_id)

    @cached_property
    def model(self):
        try:
            return apps.get_model(self.content_type)
        except (LookupError, ValueError):
            raise ApiError(
                400, 'unknown_model', "No model named %r." % (self.content_type,),
                field='target')

    @cached_property
    def field(self):
        field = get_cropduster_field(self.model, name=self.field_name)
        if field is None:
            raise ApiError(
                400, 'unknown_field',
                "%s has no cropduster field named %r."
                % (self.model._meta.label, self.field_name),
                field='target')
        return field

    @cached_property
    def instance(self):
        """Return the object being edited, or ``None``.

        ``None`` covers both an object that has not been saved yet (no
        ``object_id``) and one that has since been deleted: neither is an
        error, because the sizes a field declares are answerable without an
        instance, and the widget is routinely rendered before there is one.
        """
        if self.object_id is None:
            return None
        try:
            return self.model._default_manager.filter(pk=self.object_id).first()
        except (TypeError, ValueError):
            return None

    @cached_property
    def related_image(self):
        """Return the ``Image`` currently attached to the target field."""
        from django.contrib.contenttypes.models import ContentType
        from cropduster.models import Image

        if self.instance is None:
            return None
        return Image.objects.filter(
            content_type=ContentType.objects.get_for_model(
                self.instance, for_concrete_model=self.field.for_concrete_model),
            object_id=self.instance.pk,
            field_identifier=self.field.field_identifier).first()

    @cached_property
    def upload_to(self):
        column = get_image_column_field(self.model, self.field)
        upload_to = getattr(column, 'upload_to', None)
        if upload_to is None:
            upload_to = self.field.file_kwargs.get('upload_to')
        return upload_to or None

    @cached_property
    def sizes(self):
        """Return sizes declared by the field.

        A callable receives the target instance, or ``None`` for an unsaved
        object, and the image currently attached to the field.
        """
        sizes = self.field.sizes
        if callable(sizes):
            sizes = getattr(sizes, '__func__', sizes)
            sizes = sizes(self.instance, related=self.related_image)
        return list(sizes or [])


def parse_target(value, field='target'):
    """Parse ``content_type``, ``object_id``, and ``field_name``."""
    data = parse_json(value, field)
    if not data:
        return None
    if not isinstance(data, dict):
        raise ApiError(400, 'invalid', "%s must be an object." % field, field=field)

    content_type = data.get('content_type')
    field_name = data.get('field_name')
    if not content_type or not field_name:
        raise ApiError(
            400, 'invalid', "%s needs content_type and field_name." % field,
            field=field)
    return TargetInfo(
        content_type=content_type, field_name=field_name,
        object_id=data.get('object_id') or None)


def effective_sizes(target, client_sizes):
    """Return the declared sizes selected by a request.

    With no target the client's sizes are taken as given. With one, the sizes
    are the field's own: the client may narrow them by name (one dialog can
    be about one size), but the geometry, and so the minimum dimensions an
    upload has to satisfy, comes from the model either way.
    """
    if target is None:
        return list(client_sizes or [])

    declared = [size for size in target.sizes if not size.is_alias]
    if not client_sizes:
        return declared

    allowed = {size.name for size in declared}
    requested = [size.name for size in client_sizes]
    refused = [name for name in requested if name not in allowed]
    if refused:
        raise ApiError(
            400, 'sizes_not_allowed',
            "%s does not declare the size(s) %s."
            % (target.field_name, ', '.join(repr(name) for name in refused)),
            field='sizes',
            details={'refused': refused, 'allowed': sorted(allowed)})
    return [size for size in declared if size.name in set(requested)]


def size_by_name(sizes, name, *, field='thumbs'):
    for size in sizes:
        if not size.is_alias and size.name == name:
            return size
    raise ApiError(
        400, 'unknown_size', "No size named %r was declared." % (name,), field=field)


def limit_size_widths(sizes, max_w, image_width=None):
    """Return copies of ``sizes`` limited to ``max_w``.

    The CKEditor dialog passes ``max_w`` as the width of the column the image
    will occupy. It is ignored when the image is no wider than that already,
    exactly as the standalone dialog ignores it, and it is applied to copies
    because the sizes it applies to are the ones declared on a model class:
    shared objects that a request must not mutate.
    """
    if not max_w:
        return sizes
    if image_width and max_w >= image_width:
        return sizes

    copies = json.loads(json.dumps(sizes))
    for size in copies:
        size.max_w = min(size.max_w, max_w) if size.max_w else max_w
    return copies


def crop_suggestions(image, sizes, thumbs):
    """Return a best-fit box for each size without a crop.

    The same proposal :func:`cropduster.services.crop.apply_crops` makes for an
    uncropped size, made without rendering anything: the dialog asks for state
    before the editor has touched a crop, and every uncropped size needs a box
    to open on. The fit is computed against the image's stated dimensions
    rather than its pixels, so nothing is read from storage.
    """
    if not (image.width and image.height):
        return {}

    by_name = {thumb.name: thumb for thumb in thumbs}
    ordered = [by_name[size.name] for size in sizes if size.name in by_name]
    cropped = [thumb for thumb in ordered if thumb.crop_w and thumb.crop_h]
    if not cropped:
        return {}

    suggestions = {}
    for size in sizes:
        thumb = by_name.get(size.name)
        if thumb is not None and (thumb.pk or (thumb.crop_w and thumb.crop_h)):
            continue
        best_fit = size.fit_to_crop(
            cropped[0], original_image=(image.width, image.height))
        if best_fit:
            suggestions[size.name] = best_fit.box
    return suggestions
