"""Preserve the 4.x ``cropduster.settings`` import paths.

``cropduster.settings.CROPDUSTER_CREATE_THUMBS`` and
``from cropduster.settings import CROPDUSTER_PREVIEW_WIDTH`` remain valid.
Module ``__getattr__`` (PEP 562) forwards attribute access to the settings
object, which reads the current value from ``django.conf.settings``. A value
bound to a local name is still a snapshot, so Cropduster reads changing
settings through the module.

The module exports ``CROPDUSTER_APP_LABEL`` and ``CROPDUSTER_DB_PREFIX`` as
ordinary attributes because they are read once at import and never change.
Existing migrations also import
``cropduster.settings.CROPDUSTER_DB_PREFIX`` directly.
"""

from cropduster.conf import (  # noqa: F401
    CROPDUSTER_APP_LABEL,
    CROPDUSTER_DB_PREFIX,
    CROPDUSTER_V4_APP_LABEL,
    CROPDUSTER_V4_DB_PREFIX,
    SETTING_NAMES as _SETTING_NAMES,
    default_jpeg_quality,
    get_jpeg_quality,
    settings as _settings,
)


# Names resolved through ``__getattr__`` are not module globals; ``__all__``
# lists them so ``import *`` and ``dir()`` expose the supported settings.
__all__ = ('default_jpeg_quality', 'get_jpeg_quality') + _SETTING_NAMES


def __getattr__(name):
    try:
        return getattr(_settings, name)
    except AttributeError:
        raise AttributeError("module %r has no attribute %r" % (__name__, name))


def __dir__():
    return sorted(set(globals()) | set(__all__))
