from django import template


register = template.Library()


def scale(size, max_width=None, max_height=None):
    width_scale = height_scale = scale = 1.0

    if max_width is None and max_height is None:
        return (size.width, size.height)

    if max_width is not None:
        try:
            max_width = float(max_width)
        except TypeError:
            max_width = None

    if max_height is not None:
        try:
            max_height = float(max_height)
        except TypeError:
            max_height = None

    if max_width is not None and size.width > max_width:
        width_scale = max_width / float(size.width)
        if max_height is None:
            height = int(round(size.height * width_scale))
            return (int(max_width), height)

    if max_height is not None and size.height > max_height:
        height_scale = max_height / float(size.height)
        if max_width is None:
            width = int(round(size.width * height_scale))
            return (width, int(max_height))

    scale = min(width_scale, height_scale)

    if scale == 1.0:
        return (int(size.width), int(size.height))
    else:
        return (int(round(size.width * scale)), int(round(size.height * scale)))


@register.simple_tag
def scale_width(size, max_width=None, max_height=None):
    w, h = scale(size, max_width=max_width, max_height=max_height)
    return w


@register.simple_tag
def scale_height(size, max_width=None, max_height=None):
    w, h = scale(size, max_width=max_width, max_height=max_height)
    return h
