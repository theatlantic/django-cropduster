from django import template
register = template.Library()

@register.assignment_tag
def get_crop(image, crop_name):
    """
    Get the crop of an image. Usage:

    {% get_crop article.image 'square_thumbnail' as crop %}

    will return a dictionary of

    {
        "url": /media/path/to/my.jpg,
        "width": 150,
        "height" 150,
    }

    For use in an image tag or style block.

    """

    # If this isn't a cropduster field, abort
    if not getattr(image, 'cropduster_image', None):
        return None

    w, h = image.cropduster_image.get_image_size(crop_name)
    url = image.cropduster_image.get_image_url(crop_name)

    return {
        "width": w,
        "height": h,
        "url": url,
    }