from django import template
from cropduster.models import Image
from cropduster.resizing import Size
register = template.Library()

@register.assignment_tag
def get_crop(image, crop_name, size=None, attribution=None, exact_size=False):
    """
    Get the crop of an image. Usage:

    {% get_crop article.image 'square_thumbnail' size=1 attribution=1 as img %}

    will a dictionary to `img` that looks like:

    {
        "url": /media/path/to/my.jpg,
        "width": 150,
        "height" 150,
        "attribution": 'Stock Photoz',
        "attribution_link": 'http://stockphotoz.com',
        "caption": 'Woman laughing alone with salad.',
    }

    For use in an image tag or style block like:

        <img src="{{ img.url }}">

    Omitting the `size` kwarg will omit width and height. You usually want to do this,
    since the size lookup is a database call.

    Omitting the `attribution` kwarg will omit the attribution, attribution_link,
    and caption.
    """
    if size:
        raise DeprecationWarning("The size kwarg is deprecated.")

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
        data['width'], data['height'] = data['width'], data['height'] = image.related_object.get_image_size(size_name=crop_name)

    if attribution:
        data.update({
            "attribution": image.related_object.attribution,
            "attribution_link": image.related_object.attribution_link,
            "caption": image.related_object.caption,
        })
    return data
