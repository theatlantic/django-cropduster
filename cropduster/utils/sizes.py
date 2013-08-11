from __future__ import division
from decimal import Decimal, ROUND_HALF_DOWN
import json


__all__ = ('get_aspect_ratios', 'validate_sizes', 'get_min_size')


def get_aspect_ratios(dims):
    ratios = []
    for name in dims.keys():
        (w, h) = dims[name]
        ratio = round(w / h, 2)
        ratio = Decimal(str(ratio)).quantize(Decimal('.1'), rounding=ROUND_HALF_DOWN)
        if ratio not in ratios:
            ratios.append(ratio)
    return ratios


def validate_sizes(sizes):
    valid_sizes_msg = (
        u"It must be a dict of two-valued tuples, each keyed on the "
        u"thumbnail name.")

    if sizes is None:
        raise ValueError("The sizes attribute is None. " + valid_sizes_msg)
    elif not isinstance(sizes, dict):
        raise ValueError("The sizes attribute is invalid. " + valid_sizes_msg)
    elif len(sizes.keys()) == 0:
        raise ValueError("The sizes attribute is empty " + valid_sizes_msg)

    for size_name in sizes:
        size = sizes[size_name]
        if not isinstance(size, (tuple, list)):
            raise ValueError("The '%s' size is not a list or tuple; instead is type '%s'" % \
                    (size_name, type(size).__name__) )
        if len(size) != 2:
            raise ValueError((
                u"The '%(size_name)s' size is not a two-valued tuple, i.e. "
                u"'(width, height)'") % {'size_name': size_name})
        if (any([not(isinstance(sz, (int, long))) or sz <= 0 for sz in size])):
            raise ValueError((
                u"The '%s' size has a width or height that is not a positive "
                u"integer.") % size_name)


def get_largest_size(sizes):
    validate_sizes(sizes)
    max_w, max_h = 0, 0
    for size_name, size in sizes.items():
        (w, h) = size
        max_w = max(w, max_w)
        max_h = max(h, max_h)
    return (max_w, max_h)


def get_min_size(*args):
    """
    Determine the minimum required width and height from a list of sizes
    """
    min_w, min_h = 0, 0
    for sizes in args:
        if sizes == u'null':
            continue
        if isinstance(sizes, basestring):
            sizes = json.loads(sizes)
        if not sizes:
            continue
        # The min width and height for the image = the largest w / h of the
        # sizes / auto_sizes
        (largest_w, largest_h) = get_largest_size(sizes)
        min_w = max(largest_w, min_w)
        min_h = max(largest_h, min_h)
    return (min_w, min_h)
