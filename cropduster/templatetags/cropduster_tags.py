import time
import warnings

import six

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
def get_crop(image, crop_name, exact_size=False, **kwargs):
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

    if not image:
        return

    if "size" in kwargs:
        warnings.warn("The size kwarg is deprecated.", DeprecationWarning)

    data = {}
    data['url'] = getattr(Image.get_file_for_size(image, crop_name), 'url', None)

    if not exact_size:
        sizes = Size.flatten(image.sizes)
        try:
            size = six.next(size_obj for size_obj in sizes if size_obj.name == crop_name)
        except StopIteration:
            pass
        else:
            if size.width:
                data['width'] = size.width

            if size.height:
                data['height'] = size.height
    elif not image.related_object:
        return None
    else:
        thumbs = {thumb.name: thumb for thumb in image.related_object.thumbs.all()}
        try:
            thumb = thumbs[crop_name]
        except KeyError:
            if crop_name == "original":
                thumb = image.related_object
            else:
                return None

        cache_buster = str(time.mktime(thumb.date_modified.timetuple()))[:-2]
        data.update({
            "url": "%s?%s" % (data["url"], cache_buster),
            "width": thumb.width,
            "height": thumb.height,
            "attribution": image.related_object.attribution,
            "attribution_link": image.related_object.attribution_link,
            "caption": image.related_object.caption,
        })

    return data
