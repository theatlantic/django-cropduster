__all__ = ('get_image_storage',)


def get_image_storage():
    """Return the storage configured on ``Image.image``.

    Originals, previews, and thumbs use the same storage. It is
    ``default_storage`` unless an ``Image`` subclass overrides the field.
    """
    from cropduster.models import Image

    return Image._meta.get_field("image").storage
