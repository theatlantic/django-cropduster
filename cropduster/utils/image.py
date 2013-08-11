from __future__ import division

import PIL.Image


__all__ = ('get_image_extension', 'rescale', 'create_cropped_image')


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
