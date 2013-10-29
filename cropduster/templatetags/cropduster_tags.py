from django import template
from cropduster.models import Image
register = template.Library()

@register.assignment_tag
def get_crop(image, crop_name, size=None):
    """
    Get the crop of an image. Usage:

    {% get_crop article.image 'square_thumbnail' as size=1 %}

    will return a dictionary of

    {
        "url": /media/path/to/my.jpg,
        "width": 150,
        "height" 150,
    }

    For use in an image tag or style block.

    Omitting the `size` kwarg will omit width and height. You usually want to do this,
    since the size lookup is a database call.

    """
    data = {}
    data['url'] = getattr(Image.get_file_for_size(image, crop_name), 'url', None)
    if size:
        data['width'], data['height'] = image.cropduster_image.get_image_size(size_name=crop_name)
    return data
