from django import template
from cropduster.models import Image
register = template.Library()

@register.assignment_tag
def get_crop(image, crop_name, size=None):
    """
    Get the crop of an image. Usage:

    {% get_crop article.image 'square_thumbnail' size=1 as img %}

    will a dictionary to `img` that looks like:

    {
        "url": /media/path/to/my.jpg,
        "width": 150,
        "height" 150,
    }

    For use in an image tag or style block like:

        <img src="{{ img.url }}">

    Omitting the `size` kwarg will omit width and height. You usually want to do this,
    since the size lookup is a database call.

    """
    data = {}
    data['url'] = getattr(Image.get_file_for_size(image, crop_name), 'url', None)
    if size:
        data['width'], data['height'] = image.related_object.get_image_size(size_name=crop_name)
    return data
