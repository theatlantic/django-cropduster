import warnings

from django import template
from cropduster.models import Image
from cropduster.resizing import Size
register = template.Library()

@register.assignment_tag
def get_crop(image, crop_name, size=None, attribution=None, exact_size=False):
    """
    Get the crop of an image. Usage:

    {% get_crop article.image 'square_thumbnail' attribution=1 exact_size=1 as img %}

    will assign to `img` a dictionary that looks like:

    {
        "url": '/media/path/to/my.jpg',
        "width": 150,
        "height" 150,
        "attribution": 'Stock Photoz',
        "attribution_link": 'http://stockphotoz.com',
        "caption": 'Woman laughing alone with salad.',
    }

    For use in an image tag or style block like:

        <img src="{{ img.url }}">

    The `size` kwarg is deprecated.

    Omitting the `attribution` kwarg will omit the attribution, attribution_link,
    and caption.

    Omitting the `exact_size` kwarg will return the width and/or the height of
    the crop size that was passed in. Crop sizes do not always require both
    values so `exact_size` gives you access to the actual size of an image.
    """

    # If a dictionary is passed into get_crop instead of an image, it will be returned.
    # This allows for easier mocking.
    if isinstance(image, dict):
        return image

    if size:
        warnings.warn("The size kwarg is deprecated.", DeprecationWarning)

    data = {}
    data['url'] = getattr(Image.get_file_for_size(image, crop_name), 'url', None)

    if not exact_size:
        sizes = Size.flatten(image.sizes)
        try:
            size = next(size_obj for size_obj in sizes if size_obj.name == crop_name)
        except StopIteration:
            pass
        else:
            if size.width:
                data['width'] = size.width

            if size.height:
                data['height'] = size.height
    else:
        data['width'], data['height'] = image.related_object.get_image_size(size_name=crop_name)

    if attribution:
        data.update({
            "attribution": image.related_object.attribution,
            "attribution_link": image.related_object.attribution_link,
            "caption": image.related_object.caption,
        })
    return data
