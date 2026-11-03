import re

from . import jsonutils as json
from ..resizing import Size


__all__ = ('get_min_size', 'sanitize_size_name')


def sanitize_size_name(name):
    """Return a size name safe for template and JSON dictionary keys.

    Size names are unrestricted, and names such as ``main@2x`` cannot be
    accessed as template variables. Characters outside ``[A-Za-z0-9_-]`` are
    replaced with underscores.
    """
    return re.sub(r'[^\w\-]', '_', name)


def get_min_size(sizes):
    """Determine the minimum required width & height from a list of sizes."""
    min_w, min_h = 0, 0
    if sizes == 'null':
        return (0, 0)
    if isinstance(sizes, str):
        sizes = json.loads(sizes)
    if not sizes:
        return (0, 0)
    # The min width and height for the image = the largest w / h of the sizes
    for size in Size.flatten(sizes):
        if size.required:
            min_w = max(size.min_w, min_w)
            min_h = max(size.min_h, min_h)
    return (min_w, min_h)
