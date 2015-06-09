.. _customization

Customization
=============

Available Settings
------------------

``CROPDUSTER_JPEG_QUALITY``
    The value of the ``quality`` keyword argument passed to Pillow's ``save()`` method for JPEG files. Can be either a numeric value or a callable which gets the image's width and height as arguments and should return a numeric value.

``CROPDUSTER_PREVIEW_WIDTH``, ``CROPDUSTER_PREVIEW_HEIGHT``
    The maximum width and height, respectively, of the preview image shown in the cropduster upload dialog.

``CROPDUSTER_GIFSICLE_PATH``
    The full path to gifsicle binary. If this setting is not defined it will search for it in the ``PATH``.
