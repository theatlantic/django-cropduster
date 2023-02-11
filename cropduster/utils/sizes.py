from __future__ import division

from django.utils import six

from . import jsonutils as json
from ..resizing import Size


__all__ = ('get_min_size',)


def get_min_size(sizes):
    """Determine the minimum required width & height from a list of sizes."""
    min_w, min_h = 0, 0
    if sizes == 'null':
        return (0, 0)
    if isinstance(sizes, six.string_types):
        sizes = json.loads(sizes)
    if not sizes:
        return (0, 0)
    # The min width and height for the image = the largest w / h of the sizes
    for size in Size.flatten(sizes):
        if size.required:
            min_w = max(size.min_w, min_w)
            min_h = max(size.min_h, min_h)
    return (min_w, min_h)
