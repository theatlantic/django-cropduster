from django import template
register = template.Library()

@register.assignment_tag
def get_crop(image, crop_name, size=False):
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

    # If this isn't a cropduster field, abort
    if not getattr(image, 'cropduster_image', None):
        return None

    data = {}
    data['url'] = image.cropduster_image.get_image_url(size_name=crop_name)
    if size:
        data['width'], data['height'] = image.cropduster_image.get_image_size(size_name=crop_name)
    return data
