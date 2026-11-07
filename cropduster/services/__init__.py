"""Operations shared by Cropduster views and programmatic callers."""

import importlib

from .paths import unique_upload_dir


__all__ = (
    'CropResult', 'PreviewInfo', 'ThumbOutcome', 'ThumbRequest',
    'UploadResult', 'adopt_standalone', 'apply_crops', 'build_payload',
    'legacy_crop_response', 'payload_to_legacy', 'store_upload',
    'unique_upload_dir')


_LAZY_IMPORTS = {
    'CropResult': 'crop',
    'ThumbOutcome': 'crop',
    'ThumbRequest': 'crop',
    'apply_crops': 'crop',
    'PreviewInfo': 'upload',
    'UploadResult': 'upload',
    'adopt_standalone': 'upload',
    'store_upload': 'upload',
    'build_payload': 'payload',
    'legacy_crop_response': 'payload',
    'payload_to_legacy': 'payload',
}


def __getattr__(name):
    try:
        module_name = _LAZY_IMPORTS[name]
    except KeyError:
        raise AttributeError("module %s has no attribute %r" % (__name__, name))
    value = getattr(importlib.import_module('.%s' % module_name, __name__), name)
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(_LAZY_IMPORTS))
