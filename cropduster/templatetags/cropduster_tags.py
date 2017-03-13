import time
import warnings

import django
from django import template
from cropduster.models import Image
from cropduster.resizing import Size


register = template.Library()


if django.VERSION >= (1, 9):
    tag_decorator = register.simple_tag
else:
    tag_decorator = register.assignment_tag


@tag_decorator
def get_crop(image, crop_name, **kwargs):
    """
    Get the crop of an image. Usage:

    {% get_crop article.image 'square_thumbnail' attribution=1 as img %}

    will assign to `img` a dictionary that looks like:

    {
        "url": '/media/path/to/my.jpg',
        "width": 150,
        "height" 150,
        "attribution": 'Stock Photoz',
        "attribution_link": 'http://stockphotoz.com',
        "caption": 'Woman laughing alone with salad.',
        "alt_text": 'Woman laughing alone with salad.'
    }

    For use in an image tag or style block like:

        <img src="{{ img.url }}">

    The `exact_size` kwarg is deprecated.

    Omitting the `attribution` kwarg will omit the attribution, attribution_link,
    and caption.
    """

    if "exact_size" in kwargs:
        warnings.warn("get_crop's `exact_size` kwarg is deprecated.", DeprecationWarning)

    if not image or not image.related_object:
        return None

    url = getattr(Image.get_file_for_size(image, crop_name), 'url', None)

    thumbs = {thumb.name: thumb for thumb in image.related_object.thumbs.all()}
    try:
        thumb = thumbs[crop_name]
    except KeyError:
        if crop_name == "original":
            thumb = image.related_object
        else:
            return None

    cache_buster = str(time.mktime(thumb.date_modified.timetuple()))[:-2]
    return {
        "url": "%s?%s" % (url, cache_buster),
        "width": thumb.width,
        "height": thumb.height,
        "attribution": image.related_object.attribution,
        "attribution_link": image.related_object.attribution_link,
        "caption": image.related_object.caption,
        "alt_text": image.related_object.alt_text,
    }
