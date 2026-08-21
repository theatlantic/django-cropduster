from generic_plus.utils import get_generic_file_fields


__all__ = ('get_cropduster_fields', 'get_cropduster_field', 'get_image_column_field')


def get_cropduster_fields(model):
    """Return ``CropDusterField`` instances declared or inherited by ``model``."""
    from cropduster.fields import CropDusterField

    return [f for f in get_generic_file_fields(model) if isinstance(f, CropDusterField)]


def get_cropduster_field(model, *, name=None, field_identifier=None):
    """Return the ``CropDusterField`` on ``model`` matching the arguments.

    ``name`` matches the field's attribute name and ``field_identifier`` the
    value stored on its ``Image`` rows. Called with neither argument, the
    function returns the model's first Cropduster field. It returns ``None``
    when nothing matches because ``Image`` rows may remain after their model
    field is removed.
    """
    fields = get_cropduster_fields(model)
    if name is not None:
        fields = [f for f in fields if f.name == name]
    if field_identifier is not None:
        fields = [f for f in fields if f.field_identifier == field_identifier]
    return fields[0] if fields else None


def get_image_column_field(model, cropduster_field):
    """Return the concrete image column used by ``cropduster_field``.

    Multi-table inheritance copies the private field to the child while its
    database column remains on the parent. The copy's ``file_field`` is not
    contributed to either model and has no ``attname`` or ``model``, so the
    column is looked up in ``_meta.fields``, which includes the parent
    models' contributed fields.
    """
    from cropduster.fields import CropDusterImageField

    for field in model._meta.fields:
        if isinstance(field, CropDusterImageField) and field.name == cropduster_field.file_field_name:
            return field
    return None
