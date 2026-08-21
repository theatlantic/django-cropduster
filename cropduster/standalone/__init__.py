"""Store standalone crop geometry in the image's XMP metadata.

That metadata is read and written through libxmp and the exempi shared
library. Both are optional dependencies installed by the ``standalone`` extra.
The ``StandaloneImage`` model, its table, and its URL remain registered without
the extra because they do not import metadata support. Entry points that read
or write XMP call :func:`require_standalone`, which reports the missing extra.
"""

from django.core.exceptions import ImproperlyConfigured

from cropduster.exceptions import CropDusterConfigurationError


NOT_INSTALLED_MESSAGE = (
    "standalone mode requires the 'standalone' extra: "
    "pip install django-cropduster[standalone]")


def standalone_available():
    """Return whether standalone mode can read and write XMP metadata.

    Importing ``cropduster.standalone.metadata`` raises
    ``ImproperlyConfigured`` when libxmp or exempi is missing. Other exceptions
    are not caught. The import is attempted on every call so tests can make
    the dependency unavailable temporarily.
    """
    try:
        import cropduster.standalone.metadata  # noqa: F401
    except ImproperlyConfigured:
        return False
    return True


def require_standalone():
    if not standalone_available():
        raise CropDusterConfigurationError(NOT_INSTALLED_MESSAGE)
