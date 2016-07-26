Changelog
=========

**4.9.0 (May 13, 2016)**

* Fixed: upload and crop views now require admin login

**4.8.49 (Apr 14, 2016)**

* Fix bugs with ``regenerate_thumbs()`` when ``permissive=True``

**4.8.41 (Dec 16, 2015)**

* New: Django 1.9 support

**4.8.39 (Oct 28, 2015)**

* Fixed: bug in ``best_fit`` calculation where scaling could cause the image dimensions to drop below mins.

**4.8.38 (Oct 22, 2015)**

* Fixed: Bug where ``for_concrete_model`` might not be set correctly.

**4.8.37 (Sep 28, 2015)**

* New: Add ability to retain xmp metadata (if ``CROPDUSTER_RETAIN_METADATA = True``)

**4.8.36 (Sep 17, 2015)**

* Improved: optimized cropduster inline formset with ``prefetch_related`` on ``thumbs``

**4.8.35 (Sep 3, 2015)**

* Fixed: Initial migrations in Django 1.8.

**4.8.34 (Aug 30, 2015)**

* Fixed: The python-xmp-toolkit package is now optional.

**4.8.32 (Jul 27, 2015)**

* Improved: Drag resizing of non-corner handlers in jCrop scales in a more sensible way.

**4.8.31 (Jul 26, 2015)**

* Fixed: Center initial crop when min/max aspect ratio is specified

**4.8.30 (Jul 22, 2015)**

* Fixed: A bug in updates when CropDusterField is defined on a parent model

**4.8.28 (Jul 16, 2015)**

* Fixed: CropDusterField kwargs ``min_w``, ``min_h``, ``max_w``, and ``max_h`` now work as expected.

**4.8.26 (Jul 12, 2015)**

* Fixed: AttributeError in Django 1.6+ when using custom cropduster formfield
* Fixed: Updated django-generic-plus to fix an issue with multiple CropDusterFields spanning model inheritance.

**4.8.25 (Jul 11, 2015)**

* Fixed: Orphaned thumbs were being created when cropping images with multiple sizes (issue #41)

**4.8.23 (Jun 15, 2015)**

* Fixed: Off-by-one rounding bug in Size.fit_to_crop()

**4.8.22 (Jun 12, 2015)**

* Improved: Show help text about minimum image on upload dialog, when applicable.

**4.8.19 (Jun 9, 2015)**

* Improved: Animated GIFs are now processed by gifsicle if available
* New: Added actual documentation
* New: Add setting CROPDUSTER_JPEG_QUALITY; can be numeric or a callable

**4.8.18 (Jun 5, 2015)**

* Fixed: Non-South migrations in Django 1.7 and 1.8 were broken.
* Improved: Appearance of the cropduster widget in the Django admin without Grappelli.

**4.8.17 (May 31, 2015)**

* New: Grappelli is no longer required to use django-cropduster.
* Fixed: Python 3 bug in ``cropduster.models.Thumb.to_dict()``.

**4.8.16 (May 29, 2015)**

* New: Django 1.8 compatibility.

**4.8.15 (May 5, 2015)**

* Fixed: bug where blank ``Image.path`` prevents image upload.

**4.8.14 (Apr 28, 2015)**

* Improved: Image dimensions are no longer recalculated on every save.

**4.8.13 (Apr 21, 2015)**

* Improved: Added cachebusting to ``get_crop`` templatetag.

**4.8.10 (Apr 12, 2015)**

* New: Add ``required`` keyword argument to ``Size``, allowing for crops which are only generated if the image and crop dimensions are large enough.

**4.8.8 (Apr 10, 2015)**

* Improved: Use bicubic downsampling when generating crops with Pillow version >= 2.7.0.
* Improved: Retain ICC color profile when saving image, if Pillow has JPEG ICC support.

**4.8.7 (Mar 18, 2015)**

* Fixed: ``field_identifier`` now defaults to empty string, not ``None``.
* Fixed: Bug that caused small JPEG crops to be saved at poor quality.

**4.8.4 (Mar 5, 2015)**

* New: Give cropduster a logo.

**4.8.3 (Feb 23, 2015)**

* New: Make default JPEG quality vary based on the size of the image; add `get_jpeg_quality` setting that allows for overriding the default JPEG quality.

**4.8.0 (Feb 12, 2015)**

* New: Django 1.7 compatibility
* New: Add ``field_identifier`` keyword argument to ``CropDusterField``, which allows for multiple ``CropDusterField`` fields on a single model.
* New: Add unit tests, including Selenium tests.

**4.7.6 (Jan 21, 2015)**

* Fix: Bug in ``CropDusterImageFieldFile.generate_thumbs`` method

**4.7.5 (Jan 21, 2015)**

* New: Add ``CropDusterImageFieldFile.generate_thumbs`` method, which generates and updates crops for a ``CropDusterField``.

**4.7.4 (Dec 17, 2014)**

* Improved: Height of CKEditor dialog for smaller monitors.
* Improved: Add convenience ``@property`` helpers: ``Thumb.image_file``, ``Thumb.url``, ``Thumb.path``, and ``Image.url``.
* Improved: Use filters passed to ``limit_choices_to`` keyword argument in ``ReverseForeignRelation``.

**4.7.3 (Nov 25, 2014)**

* Fixed: Regression from 4.7.2 where ``get_crop`` templatetag did not always return an image.

**4.7.1 (Oct 16, 2014)**

* Improved: ``Image.caption`` field no longer has a maximum length.

**4.6.4 (Jul 10, 2014)**

* Fixed: Querysets of the form ``Image.objects.filter(thumbs__x=...)``.
* Improved: Disable "Upload" button before a file has been chosen.
* Fixed: Error in CKEditor widget triggered by user clicking the "OK" button without uploading an image.

**4.6.3 (Jul 9, 2014)**

* Fixed: Python 3 regression that raised ``ValueError`` when the form received an empty string for the ``thumbs`` field.
* Improved: Style and functionality of the delete checkbox.

**4.6.2 (Jul 9, 2014)**

* Fixed: Deleting a cropduster image did not clear the file field on the generic-related instance, which caused cropduster to subsequently render file widgets in legacy mode.

**4.6.1 (Jul 8, 2014)**

* Fixed: Bug that prevented CKEditor plugin from downloading external images already existing in WYSIWYG.

**4.6.0 (Jul 8, 2014)**

* Python 3 compatibility
* Django 1.6 compatibility
* Removed: Dependency on ``jsonutils``.
* Improved: Support ``python-xmp-toolkit`` 2.0.0+.
