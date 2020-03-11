from __future__ import division

from io import BytesIO
import os
import warnings
import math
from distutils.version import LooseVersion

import PIL.Image
from PIL import ImageFile, JpegImagePlugin

from django.core.files.storage import default_storage
from django.utils import six
from django.utils.six.moves import xrange

from cropduster.settings import (
    get_jpeg_quality, JPEG_SAVE_ICC_SUPPORTED, CROPDUSTER_GIFSICLE_PATH)

from .gifsicle import GifsicleImage


__all__ = (
    'get_image_extension', 'is_transparent', 'exif_orientation',
    'correct_colorspace', 'is_animated_gif', 'has_animated_gif_support',
    'process_image', 'smart_resize')


# workaround for https://github.com/python-pillow/Pillow/issues/1138
# without this hack, pillow misidenfifies some jpeg files as "mpo" files
JpegImagePlugin._getmp = lambda x: None  # noqa

ImageFile.MAXBLOCK = 4096 * 4096 * 8


IMAGE_EXTENSIONS = {
    "ARG":  ".arg",   "BMP":  ".bmp",   "BUFR": ".bufr",  "CUR":  ".cur",   "DCX":  ".dcx",
    "EPS":  ".ps",    "FITS": ".fit",   "FLI":  ".fli",   "FPX":  ".fpx",   "GBR":  ".gbr",
    "GIF":  ".gif",   "GRIB": ".grib",  "HDF5": ".hdf",   "ICNS": ".icns",  "ICO":  ".ico",
    "IM":   ".im",    "IPTC": ".iim",   "JPEG": ".jpg",   "MIC":  ".mic",   "MPEG": ".mpg",
    "MSP":  ".msp",   "Palm": ".palm",  "PCD":  ".pcd",   "PCX":  ".pcx",   "PDF":  ".pdf",
    "PNG":  ".png",   "PPM":  ".ppm",   "PSD":  ".psd",   "SGI":  ".rgb",   "SUN":  ".ras",
    "TGA":  ".tga",   "TIFF": ".tiff",  "WMF":  ".wmf",   "XBM":  ".xbm",   "XPM":  ".xpm",
    "MPO":  ".jpg",  # Pillow mislabels some jpeg images as MPO files
}


def get_image_extension(img):
    if img.format in IMAGE_EXTENSIONS:
        return IMAGE_EXTENSIONS[img.format]
    else:
        for ext, format in six.iteritems(PIL.Image.EXTENSION):
            if format == img.format:
                return ext
        # Our fallback is the PIL format name in lowercase,
        # which is probably the file extension
        return ".%s" % img.format.lower()


def is_transparent(image):
    """
    Check to see if an image is transparent.
    """
    if not isinstance(image, PIL.Image.Image):
        # Can only deal with PIL images, fall back to the assumption that that
        # it's not transparent.
        return False
    return (image.mode in ('RGBA', 'LA') or
            (image.mode == 'P' and 'transparency' in image.info))


def exif_orientation(im):
    """
    Rotate and/or flip an image to respect the image's EXIF orientation data.
    """
    try:
        exif = im._getexif()
    except (AttributeError, IndexError, KeyError, IOError):
        exif = None
    if exif:
        orientation = exif.get(0x0112)
        if orientation == 2:
            im = im.transpose(PIL.Image.FLIP_LEFT_RIGHT)
        elif orientation == 3:
            im = im.rotate(180)
        elif orientation == 4:
            im = im.transpose(PIL.Image.FLIP_TOP_BOTTOM)
        elif orientation == 5:
            im = im.rotate(-90).transpose(PIL.Image.FLIP_LEFT_RIGHT)
        elif orientation == 6:
            im = im.rotate(-90)
        elif orientation == 7:
            im = im.rotate(90).transpose(PIL.Image.FLIP_LEFT_RIGHT)
        elif orientation == 8:
            im = im.rotate(90)
    return im


def correct_colorspace(im, bw=False):
    """
    Convert images to the correct color space.

    bw
        Make the thumbnail grayscale (not really just black & white).
    """
    if bw:
        if im.mode in ('L', 'LA'):
            return im
        if is_transparent(im):
            return im.convert('LA')
        else:
            return im.convert('L')

    if im.mode in ('L', 'RGB'):
        return im

    return im.convert('RGB')


def is_animated_gif(im):
    info = getattr(im, 'info', None) or {}
    return bool((im.format == 'GIF' or not im.format) and info.get('extension'))


def has_animated_gif_support():
    return bool(CROPDUSTER_GIFSICLE_PATH)


def process_image(im, save_filename=None, callback=lambda i: i, nq=0, save_params=None):
    is_animated = is_animated_gif(im)
    images = [im]

    if is_animated:
        if not CROPDUSTER_GIFSICLE_PATH:
            warnings.warn(
                u"This server does not have animated gif support; your uploaded image "
                u"has been made static.")
        else:
            images = [GifsicleImage(im)]

    new_images = [callback(i) for i in images]

    if is_animated and not save_filename:
        raise Exception("Animated gifs must be saved on each processing.")

    if save_filename:
        save_params = save_params or {}
        if im.format == 'JPEG':
            save_params.setdefault('quality', get_jpeg_quality(new_images[0].size[0], new_images[0].size[1]))
        if im.format in ('JPEG', 'PNG') and JPEG_SAVE_ICC_SUPPORTED:
            save_params.setdefault('icc_profile', im.info.get('icc_profile'))
        img = new_images[0]
        buf = BytesIO()
        img.save(buf, format=im.format, **save_params)
        with default_storage.open(save_filename, 'wb') as f:
            f.write(buf.getvalue())
        with default_storage.open(save_filename, mode='rb') as f:
            content = f.read()
            pil_image = PIL.Image.open(BytesIO(content))
        pil_image.filename = save_filename
        return pil_image

    return new_images[0]


def smart_resize(im, final_w, final_h):
    """
    Resizes a given image in multiple steps to ensure maximum quality and performance

    :param im: PIL.Image instance the image to be resized
    :param final_w: int the intended final width of the image
    :param final_h: int the intended final height of the image
    """

    (orig_w, orig_h) = im.size
    if orig_w <= final_w and orig_h <= final_h:
        # If the image is already the right size, don't change it
        return im

    # Pillow 2.7.0 greatly improved the bicubic resize algorithm, which makes
    # our multiple-step resizing unnecessary
    pillow_version = getattr(PIL, 'PILLOW_VERSION', None)
    if pillow_version and LooseVersion(pillow_version) >= LooseVersion('2.7.0'):
        return im.resize((final_w, final_h), PIL.Image.BICUBIC)

    # Attempt to resize the image 1/8, 2/8, such that it is at least 1.5x bigger
    # than the final size
    # (Libjpg-Turbo has optimizations for resizing images by a ratio of eights)
    (goal_w, goal_h) = (final_w * 1.5, final_h * 1.5)
    # Ratios from 1/8, 2/8... 7/8
    for i in xrange(1, 8):
        ratio = i / 8
        scaled_w = orig_w * ratio
        scaled_h = orig_h * ratio
        if scaled_w >= goal_w and scaled_h >= goal_h:

            # The image may need to be cropped slightly to ensure an even
            # size reduction
            crop_w = orig_w % 8
            crop_h = orig_h % 8
            if not crop_w or not crop_h:
                im.crop((math.floor(crop_w / 2),
                         math.floor(crop_h / 2),
                         orig_w - math.ceil(crop_w / 2),
                         orig_h - math.ceil(crop_h / 2)))
                (orig_w, orig_h) = im.size

            # Resize part of the way using the fastest algorithm
            im = im.resize((int(orig_w * ratio), int(orig_w * ratio)),
                           PIL.Image.NEAREST)
            break

    # Return the image with the final resizing done at best quality
    return im.resize((final_w, final_h), PIL.Image.ANTIALIAS)
