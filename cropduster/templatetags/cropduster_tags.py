from django import template
from cropduster.models import Image
register = template.Library()

@register.assignment_tag
def get_crop(image, crop_name, size=None):
    """
    Get the crop of an image. Usage:

    {% get_crop article.image 'square_thumbnail' size=1 as crop %}

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


@register.assignment_tag
def get_best_crop(image, *args, **kwargs):
    """
    Get the first the these crops for an image.
    This is useful when you might want to fall back to another size.
    if your preferred size doesn't exist.

    {% get_best_crop article.image 'square_thumbnail' 'almost_square_thumbnail' 'original' size=1 as crop %}

    """
    crop_names = list(args)
    size = kwargs.pop('size', None)

    data = {}
    crops = list(image.cropduster_image.thumbs.filter(name__in=crop_names).values_list('name', flat=True))
    
    # If we've got nothing, we might just want to use the original in its place.
    if not crops and 'original' in crop_names:
        data['url'] = image.cropduster_image.get_image_url()
        if size:
            data['width'], data['height'] = image.cropduster_image.get_image_size()
        return data

    # Get the best crop in the order they were presented
    for crop_name in crop_names:
        if crop_name in crops:
            data['url'] = image.cropduster_image.get_image_url(crop_name)
            if size:
                data['width'], data['height'] = image.cropduster_image.get_image_size(size_name=crop_name)
            break

    return data

