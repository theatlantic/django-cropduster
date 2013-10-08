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
