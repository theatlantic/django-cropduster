from django.conf import settings

from coffin import template
from coffin.template.loader import get_template

from cropduster.models import Size

register = template.Library()

# This is cached across requests. Do we want that?
image_sizes = Size.objects.all()
image_size_map = {}
for size in image_sizes:
    image_size_map[(size.size_set_id, size.slug)] = size


@register.object
def get_image(image, size_name='large', template_name='image.html', width=None, height=None, **kwargs):
    if image:
        image_url = image.thumbnail_url(size_name)
        if image_url is None or image_url == '':
            return ''
        try:
            image_size = image_size_map[(image.size_set_id, size_name)]
        except KeyError:
            return ''

        kwargs.update({
            'image_url': image_url,
            'width': width or image_size.width or '',
            'height': height or image_size.height  or '',
            'size_name': size_name,
            'attribution': image.attribution,
            'alt': kwargs.get('alt', image.caption),
        })
        kwargs['title'] = kwargs.get('title', kwargs['alt'])

        if getattr(settings, 'CROPDUSTER_KITTY_MODE', False):
            kwargs['image_url'] = "http://placekitten.com/{0}/{1}".format(
                kwargs['width'], kwargs['height'])

        tpl = get_template('templatetags/' + template_name)
        ctx = template.Context(kwargs)
        return tpl.render(ctx)
    else:
        return ''
