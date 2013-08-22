from __future__ import division

import PIL.Image


__all__ = ('get_image_extension')


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
