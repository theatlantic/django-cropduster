from __future__ import division

import os
import tempfile
import warnings

import PIL.Image

try:
    import numpy
except ImportError:
    numpy = None

try:
    import scipy
except ImportError:
    scipy = None

from .images2gif import read_gif, write_gif


__all__ = (
    'get_image_extension', 'is_transparent', 'exif_orientation',
    'correct_colorspace', 'is_animated_gif', 'has_animated_gif_support',
    'process_image')


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
        for ext, format in PIL.Image.EXTENSION.iteritems():
            if format == img.format:
                return ext
        # Our fallback is the PIL format name in lowercase,
        # which is probably the file extension
        return ".%s" % img.format.lower()


def is_transparent(image):
    """
    Check to see if an image is transparent.
    """
    if not isinstance(image, PIL.Image.PIL.Image):
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
    return bool(numpy and scipy)


def process_image(im, save_filename=None, callback=lambda i: i, nq=0, save_params=None):
    is_animated = is_animated_gif(im)
    images = [im]

    dispose = None

    if is_animated:
        if not has_animated_gif_support():
            warnings.warn(
                u"This server does not have animated gif support; your uploaded image "
                u"has been made static.")
        else:
            filename = getattr(im, 'filename', None)
            if not filename or not os.path.exists(filename):
                temp_file = tempfile.NamedTemporaryFile(suffix='.gif')
                filename = temp_file.name
                im.save(filename)

            contents = b''
            with open(filename) as f:
                contents += f.read()

            try:
                graphics_control_ext_offset = contents.index('\x21\xF9\x04')
            except ValueError:
                pass
            else:
                try:
                    dispose_byte = contents[graphics_control_ext_offset + 3]
                except IndexError:
                    pass
                else:
                    dispose = ord(dispose_byte) >> 2

            images = read_gif(filename, as_numpy=False)

    new_images = [callback(i) for i in images]

    if len(images) > 1 and not save_filename:
        raise Exception("Animated gifs must be saved on each processing.")

    if save_filename:
        # Only true if animated gif supported and multiple frames in image
        if is_animated and len(images) > 1:
            duration_ms = im.info.get('duration') or 100
            duration = float(duration_ms) / 1000.0
            repeat = True
            if im.info.get('loop', 0) != 0:
                repeat = im.info['loop']
            write_gif(save_filename, new_images, duration=duration, repeat=repeat, nq=nq, dispose=dispose)
        else:
            save_params = save_params or {}
            if im.format == 'JPEG':
                save_params.setdefault('quality', 95)
            new_images[0].save(save_filename, **save_params)

        return PIL.Image.open(save_filename)

    return new_images[0]
