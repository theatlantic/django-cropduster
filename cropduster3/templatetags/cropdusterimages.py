from coffin import template

register = template.Library()


@register.simple_tag
def get_image(image, size_name='large', template_name='image.html',
              width=None, height=None, css_class=None, **kwargs):

    if not image:
        return ""

    thumb = image.get_thumbnail(size_name)
    if thumb is None:
        return ''

    kwargs.update({
        'image_url': thumb.get_absolute_url(),
        'width': width or thumb.width,
        'height': height or thumb.height,
        'size_name': thumb.size.name,
        'attribution': image.metadata.attribution,
        'alt': kwargs.get('alt', image.metadata.caption),
        'class': css_class,
    })
    kwargs['title'] = kwargs.get('title', kwargs['alt'])

    tpl = template.loader.get_template('templatetags/' + template_name)
    ctx = template.Context(kwargs)
    return tpl.render(ctx)


@register.assignment_tag
def get_v3_crop(image, crop_name, size=None):
    """
    This uses the same API as the v4 get_crop for easy upgrading.
    
    Get the crop of an image. Usage:

    {% get_v3_crop article.image 'square_thumbnail' as size=1 %}

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
    crop = image.get_thumbnail(crop_name)
    if crop:
        data['url'] = crop.image.url
    if size:
        data['width'] = crop.width
        data['height'] = crop.height
    return data
