from django.conf import settings

from coffin import template
from coffin.template.loader import get_template

from cropduster.models import Size

register = template.Library()

@register.object
def get_image(image, size_name='large', template_name='image.html', width=None, height=None, **kwargs):
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
    })
    kwargs['title'] = kwargs.get('title', kwargs['alt'])

    tpl = get_template('templatetags/' + template_name)
    ctx = template.Context(kwargs)
    return tpl.render(ctx)

