.. _customization:

Customization
=============

Available Settings
------------------

``CROPDUSTER_JPEG_QUALITY``
    The ``quality`` keyword passed to Pillow's ``save()`` method for JPEG
    files. It may be a number or a callable that accepts the image's width and
    height and returns a number.

``CROPDUSTER_PREVIEW_WIDTH``, ``CROPDUSTER_PREVIEW_HEIGHT``
    The maximum width and height, respectively, of the preview image shown in
    the Cropduster upload dialog.

``CROPDUSTER_GIFSICLE_PATH``
    The full path to the gifsicle binary. When this setting is not defined,
    Cropduster searches ``PATH``.

``CROPDUSTER_DIALOG_MODE``
    How the crop dialog opens. ``"modal"`` keeps it in the current
    page, and ``"window"`` opens a popup. ``"auto"`` (the default) uses the
    modal when the viewport is at least 900x600 and the popup otherwise.
    ``manage.py check`` reports another value as ``cropduster.E003``.

``CROPDUSTER_DEV_SERVER_URL``
    Base URL of a running Vite development server, such as
    ``"http://localhost:5173/"``. When this setting and ``DEBUG`` are both
    enabled, the widget emits the react-refresh preamble that
    ``@vitejs/plugin-react`` requires on pages Vite does not serve itself,
    then loads ``@vite/client`` and the frontend entry module from Vite
    instead of the packaged JavaScript and CSS. The entry module imports the
    widget's CSS, which Vite injects into the page. If either setting is
    disabled, the widget uses the packaged bundle.

``CROPDUSTER_MEDIA_ROOT``
    Directory in which Cropduster writes uploaded originals and rendered
    crops. The default is ``MEDIA_ROOT``.

``CROPDUSTER_RETAIN_METADATA``
    When true, the source image's XMP metadata is copied to its rendered
    crops. The default is false. This feature requires ``libxmp`` from the ``standalone`` extra.

``CROPDUSTER_DB_PREFIX``
    Prefix for Cropduster's three table names; the default is
    ``"cropduster4"``. This allows a 3.x installation to use separate tables.
    Cropduster reads the setting at import time because the model ``Meta``
    classes use it. ``CROPDUSTER_APP_LABEL`` must remain ``"cropduster"``
    because the existing migrations use that label; ``cropduster.E010``
    reports another value.

Settings documented elsewhere
-----------------------------

``CROPDUSTER_URL_RENDERER`` and ``CROPDUSTER_THUMBOR`` are covered under
:doc:`renderers`, along with ``CROPDUSTER_CREATE_THUMBS`` and metadata-only
mode. ``CROPDUSTER_API_PERMISSION``, ``CROPDUSTER_LEGACY_CSRF_EXEMPT`` and
``CROPDUSTER_REMOTE_IMAGE_FETCH`` are covered under :doc:`http_api`.

Field arguments
---------------

``CropDusterField(dialog_mode=...)``
    Sets ``"auto"``, ``"modal"`` or ``"window"`` for one field. It overrides
    ``CROPDUSTER_DIALOG_MODE``. When the argument is ``None``, the setting is
    used::

        class Article(models.Model):
            lead_image = CropDusterField(
                upload_to="img/articles/%Y", sizes=LEAD_IMAGE_SIZES,
                dialog_mode="window")

    Any other value raises ``ImproperlyConfigured`` at import time. The
    argument does not change the field's schema or generate a migration.

    .. warning::

       Forcing ``"modal"`` bypasses the viewport check. A 960x650 dialog does
       not fit inside a smaller non-scrolling iframe, and the crop button may
       be unreachable. Use ``"window"`` for that field, or retain ``"auto"``
       so Cropduster selects the popup for the smaller viewport.

``CropDusterField(require_alt_text=True)``
    Requires alt text before an image on this field can be saved.
