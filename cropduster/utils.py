from __future__ import division

import os
import re
from datetime import datetime
from decimal import Decimal, ROUND_HALF_DOWN

from django.conf import settings
from django.template.defaultfilters import slugify

import PIL.Image
import json


MEDIA_ROOT = os.path.abspath(settings.MEDIA_ROOT)

re_media_root = re.compile(r'^%s' % re.escape(MEDIA_ROOT))
re_media_url = re.compile(r'^%s' % re.escape(settings.MEDIA_URL))
re_url_slashes = re.compile(r'(?:\A|(?<=/))/')
re_path_slashes = re.compile(r'(?<=/)/')


IMAGE_EXTENSIONS = {
    "ARG":  ".arg",   "BMP":  ".bmp",   "BUFR": ".bufr",  "CUR":  ".cur",   "DCX":  ".dcx",
    "EPS":  ".ps",    "FITS": ".fit",   "FLI":  ".fli",   "FPX":  ".fpx",   "GBR":  ".gbr",
    "GIF":  ".gif",   "GRIB": ".grib",  "HDF5": ".hdf",   "ICNS": ".icns",  "ICO":  ".ico",
    "IM":   ".im",    "IPTC": ".iim",   "JPEG": ".jpg",   "MIC":  ".mic",   "MPEG": ".mpg",
    "MSP":  ".msp",   "Palm": ".palm",  "PCD":  ".pcd",   "PCX":  ".pcx",   "PDF":  ".pdf",
    "PNG":  ".png",   "PPM":  ".ppm",   "PSD":  ".psd",   "SGI":  ".rgb",   "SUN":  ".ras",
    "TGA":  ".tga",   "TIFF": ".tiff",  "WMF":  ".wmf",   "XBM":  ".xbm",   "XPM":  ".xpm",
}


def get_image_extension(img):
    if img.format in IMAGE_EXTENSIONS:
        return IMAGE_EXTENSIONS[img.format]
    else:
        # Our fallback is the PIL format name in lowercase,
        # which is probably the file extension
        fallback_ext = ".%s" % img.format.lower()
        if fallback_ext in PIL.Image.EXTENSION:
            return fallback_ext
        exts = []
        for ext in PIL.Image.EXTENSION:
            if PIL.Image.EXTENSION[ext] == img.format:
                exts.append(ext)
        if len(exts) > 0:
            return exts[0]
        else:
            return fallback_ext


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


def get_media_path(url):
    """Determine media URL's system file."""
    path = MEDIA_ROOT + '/' + re_media_url.sub('', url)
    return re_path_slashes.sub('', path)


def get_relative_media_url(path):
    """Determine system file's media URL without MEDIA_URL prepended."""
    url = re_media_root.sub('', path)
    return re_url_slashes.sub('', url)


def get_media_url(path):
    """Determine system file's media URL."""
    url = settings.MEDIA_URL + re_media_root.sub('', os.path.abspath(path))
    return re_path_slashes.sub('', url)


def get_available_name(dir_name, file_name):
    """
    Create a folder based on file_name and return it.

    If a folder with file_name already exists in the given path,
    create a folder with a unique sequential number at the end.
    """
    file_root, extension = os.path.splitext(file_name)
    file_root = slugify(file_root)
    name = os.path.join(dir_name, file_root)

    # If the filename already exists, keep adding a higher number
    # to the folder name until the generated folder doesn't exist.
    i = 2
    while os.path.exists(name):
        # file_ext includes the dot.
        name = os.path.join(dir_name, file_root + '-' + str(i))
        i += 1
    os.makedirs(name)

    return name


def get_upload_foldername(file_name, upload_to=None):
    # Generate date based path to put uploaded file.
    date_path = datetime.now().strftime('%Y/%m')

    paths = filter(None, [settings.MEDIA_ROOT, upload_to, date_path])
    upload_path = os.path.join(*paths)

    # Make sure upload_path exists.
    if not os.path.exists(upload_path):
        os.makedirs(upload_path)

    # Get available name and return.
    return get_available_name(upload_path, file_name)


def rescale(img, w=0, h=0, crop=True):
    """
    Rescale the given image, optionally cropping it to make sure the result
    image has the specified width and height.
    """
    if w <= 0 or h <= 0:
        raise ValueError("Width and height must be greater than zero")

    src_w, src_h = img.size
    dst_w, dst_h = w, h

    src_ratio = src_w / src_h
    dst_ratio = dst_w / dst_h

    if crop:
        if dst_ratio < src_ratio:
            crop_h = src_h
            crop_w = int(crop_h * dst_ratio)
            x = int(float(src_w - crop_w) / 2)
            y = 0
        else:
            crop_w = src_w
            crop_h = int(crop_w / dst_ratio)
            x = 0
            y = int(float(src_h - crop_h) / 3)

        img = img.crop((x, y, x + crop_w, y + crop_h))

    img = img.resize((dst_w, dst_h), PIL.Image.ANTIALIAS)

    return img


def create_cropped_image(path=None, x=0, y=0, w=0, h=0):
    if path is None:
        raise ValueError("A path must be specified")
    if w <= 0 or h <= 0:
        raise ValueError("Width and height must be greater than zero")

    img = PIL.Image.open(path)
    img.copy()
    img.load()
    img = img.crop((x, y, x + w, y + h))
    img.load()
    return img
