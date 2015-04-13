import warnings

import six

from django import template
from cropduster.models import Image
from cropduster.resizing import Size


register = template.Library()


@register.assignment_tag
def get_crop(image, crop_name, **kwargs):
    """
    Get the crop of an image. Usage:

    {% get_crop article.image 'square_thumbnail' as img %}

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
    """

    if not image or not image.related_object:
        return None

    if len(kwargs) > 0:
        warnings.warn("All get_crop kwargs have been deprecated", DeprecationWarning)

    data = {}
    thumbs = {thumb.name: thumb for thumb in image.related_object.thumbs.all()}
    try:
        thumb = thumbs[crop_name]
    except KeyError:
        if crop_name == "original":
            thumb = image.related_object
        else:
            return None

    data.update({
        "url": Image.get_file_for_size(image=image, size_name=crop_name).url,
        "width": thumb.width,
        "height": thumb.height,
        "attribution": image.related_object.attribution,
        "attribution_link": image.related_object.attribution_link,
        "caption": image.related_object.caption,
    })
    return data
