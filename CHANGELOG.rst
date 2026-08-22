Changelog
=========

**5.0.0 (unreleased)**

Cropduster 5.0 replaces the admin frontend, adds versioned JSON and Python
APIs, and moves URL rendering and programmatic image attachment into
Cropduster. It does not add migrations or change the formset values written by
the widget. To upgrade, update the package versions and run ``collectstatic``;
to roll back, restore the previous versions and run ``collectstatic`` again.
See ``docs/upgrading-5.0.rst`` for the complete procedure.

Requires Python 3.10+ and Django 4.2+.

*Frontend rewrite*

* The admin JavaScript is a React 19 + TypeScript application (``frontend/``),
  built by Vite into ``cropduster/static/cropduster/dist/cropduster.js`` and
  ``cropduster.css``. The built files are committed, so installing the package
  never requires Node. ``CropDusterWidget.media`` names those two files and
  nothing else: neither ``admin/js/jquery.init.js`` nor jsrender is loaded any
  more.
* The widget mounts as a ``<cropduster-widget>`` custom element rendered by
  ``custom_field.html``. The existing hidden inline formset remains
  authoritative: the server renders it, React does not control it, and React
  renders no ``<input name=...>`` elements of its own. The ``.cropduster-*``
  class names, the ``{prefix}-N-field`` naming and ``inline.html`` are
  unchanged.
* The change form and crop dialog load their previews from the configured
  ``CROPDUSTER_URL_RENDERER``. The server and dialog write the renderer URL
  and ``srcset`` to new ``data-renderer-url`` and
  ``data-renderer-srcset`` attributes on each thumb ``<option>``. Preview
  metadata includes the corresponding renderer URL and ``srcset`` alongside
  the stored URL. ``ThumborRenderer`` includes a 2x candidate when the crop
  box or original preview has enough pixels. The serializers continue to
  write stored-file URLs to ``data-url`` and ``data-preview-url``, using
  values that are byte-for-byte identical to those written by 4.x, because
  downstream scripts read filenames from those attributes.
* The rewritten ``window.CropDuster`` keeps the same DOM effects. ``show``,
  ``complete``, ``setThumbnails``, ``createThumbnails``, ``registerInput``,
  ``removeSize``, ``restoreSize`` and ``mediaUrl`` behave as they did,
  including in-place mutation of the shared ``.data('sizes')`` array.
* ``cropduster:update`` fires on every jQuery instance found on the page with
  its ``(event, prefix, data)`` signature, and additionally as a native
  ``CustomEvent`` with ``detail = {prefix, data}``. The new
  ``cropduster:sizeschange`` ``CustomEvent`` will replace the
  ``.data('sizes')`` channel in 6.0.
* The dialog renders into an open shadow root in both presentations, so admin
  themes no longer style its internals. Every existing element ID
  (``#cropbox``, ``#crop-button``, ``#upload-button``,
  ``#id_size-width``, ...) keeps its name inside that root.
* The crop geometry is a line-for-line port of the 4.x dialog. Vitest compares
  it with 2,114 vectors extracted from 4.15.0's ``upload.js`` before the
  rewrite and 13 explicit edge cases. The extraction scripts remain under
  ``frontend/tests/legacy/``.
* The dialog's navigation arrows are real ``<button>`` elements, so the crop
  steps can be reached from the keyboard.
* The in-repo CKEditor 4 plugin uses a new
  ``CropDusterDialog.commit()`` / ``.canCommit()`` API instead of clicking
  ``#crop-button`` through jQuery. Buttons have both the ``.disabled`` class
  and the real ``disabled`` attribute.
* Vite generates ``cropduster/static/cropduster/dist/LICENSES.txt`` from the
  packages it bundles (React, ReactDOM, react-image-crop and Scheduler).
* When ``CROPDUSTER_DEV_SERVER_URL`` and ``DEBUG`` are both enabled, the widget
  loads from a running Vite development server instead of the built bundle.

*Dialog modes*

* The same dialog can render in an in-page modal, a full page, or the 4.x
  ``window.open`` popup. The presentation comes from
  ``CROPDUSTER_DIALOG_MODE``, which defaults to ``"auto"``: the modal when the
  viewport is at least 900x600, and the popup otherwise. This allows a change form in a small
  iframe to use the popup. The standalone (WYSIWYG) view is always full-page.
* ``CropDusterField(dialog_mode="window")`` overrides the setting for one
  field. This changes only its presentation and requires no migration or
  schema change.
* In modal mode the dialog retains the row from which it was opened. This fixes
  the 4.x bug where reordering a nested inline while the popup was open wrote
  the crop to the wrong row. Window mode resolves the row by prefix on
  completion, exactly as 4.x did.

*JSON API*

* The new ``cropduster/api/v1/`` routes are ``state/`` (URL-encoded dialog
  hydration), ``upload/`` (multipart) and ``crop/`` (JSON). All three are
  CSRF-protected POST endpoints with HTTP status codes and errors as
  ``{"error": {"code", "message", "field", "details"}}``.
* All three endpoints and ``AttachResult.payload()`` return the same version 1
  fields: ``image``, ``preview``, ``sizes``, ``thumbs``, ``metadata`` and
  ``warnings``. Each thumb contains the ``url`` returned by the configured
  renderer, the storage ``file_url``, ``srcset`` and ``source: null``. The
  ``source`` field is reserved for per-size override sources. ``preview``
  contains the same ``url``/``file_url`` pair.
* ``upload/`` accepts ``for_size=<name>`` to limit minimum-size validation to
  one size.
* ``crop/`` accepts a ``target`` (``content_type``, ``object_id``,
  ``field_name``). When it is present, the server derives ``upload_to`` and the
  size geometry from the field and verifies that the client's size names are a
  subset. It does not trust the minimum dimensions sent by the client.
* ``CROPDUSTER_API_PERMISSION`` names the callable that authorizes API
  requests. The default requires staff plus the model permission when a target
  is present; returning ``False`` rejects the request.
  ``cropduster.api.permissions.login_required_only`` is included for clients
  that need the 4.x authentication behavior.
* The server derives the owning target from saved image ids and stored names
  when the request omits it. Image and crop ids are checked against that owner
  and size before file access, and invalid or out-of-bounds crop boxes fail
  before any files or rows are written.
* The 4.x endpoints (``cropduster/upload/``, ``cropduster/crop/``) are still
  mounted and still CSRF-exempt. Their normalized responses match 4.15.0
  except that ``crop.sizes`` now contains the posted list instead of ``null``.

*Programmatic API*

* ``cropduster.attach(instance, field_name, source, ...)`` accepts a path, URL,
  ``File``, PIL image, ``Image`` or ``FieldFile``. It attaches the image,
  renders the sizes and returns an ``AttachResult`` (``image``, ``thumbs``,
  ``errors``, ``warnings``, ``payload(legacy=, sanitize=)``,
  ``orphan_thumbs()``).
* ``cropduster.copy_image()`` copies an existing cropduster image onto another
  field, reusing crops where they fit.
* ``cropduster.choose_crop()``, ``cropduster.thumb_for_size()``,
  ``Image.best_thumb_for_size()`` and ``crop_overlap()`` pick the best existing
  crop for a requested size.
* ``attach``, ``copy_image``, ``choose_crop``, ``thumb_for_size`` and
  ``get_renderer`` are lazily re-exported from ``cropduster`` itself; importing
  the package still does not require configured settings.
* ``cropduster.services`` defines ``store_upload()``, ``apply_crops()``,
  ``build_payload()`` and ``payload_to_legacy()``. Both response formats and
  the programmatic API call these services; the legacy views adapt their
  results to the 4.x format.
* ``attach(sources=...)`` accepts the per-size override-source argument but
  raises ``NotImplementedError``. The argument is included so a future
  implementation can use the same payload format; alternate sources are not
  supported in 5.0.
* The new ``ImageTooSmallError`` exception stores
  ``min_size``/``actual_size``, and its ``str()`` is the message shown to the
  editor. ``CropDusterFileMissing`` and ``CropDusterConfigurationError`` are
  also new.

*Renderers*

* ``CROPDUSTER_URL_RENDERER`` names the renderer that builds crop URLs.
  ``FileRenderer`` (the default) reproduces the 4.x ``?mod=`` cache-busted file
  URLs for query-free storage URLs. It leaves an existing query unchanged
  because storage may have signed it. ``ThumborRenderer`` signs Thumbor URLs
  and needs the ``thumbor`` extra.
* ``Thumb.get_url()`` and ``Thumb.get_srcset()`` call the configured renderer.
  ``{% get_crop %}`` now supports ``srcset``, retains its ``"original"``
  fallback, and accepts the same keyword arguments as before. The new
  ``{% get_thumbs %}`` tag returns crop entries keyed by size and keeps the
  image fields under ``metadata``.
* ``Image.objects.with_thumbs()`` and ``ThumbQuerySet.with_reference_thumbs()``
  prefetch the reference thumbs that URL building needs, replacing per-object
  cache-priming loops.
* With ``CROPDUSTER_CREATE_THUMBS = False`` (metadata-only mode), no
  derivative files are written. ``Crop``, ``fit_to_crop`` and
  ``Thumb.crop`` accept ``(width, height)`` tuples so geometry can be computed
  without opening an image. ``Crop.create_image()`` raises
  ``CropDusterFileMissing`` when a caller attempts to create a file without
  pixel data.
* New system checks: ``cropduster.E001`` (unloadable renderer),
  ``cropduster.E002`` (unloadable API permission), ``cropduster.E003``
  (unknown ``CROPDUSTER_DIALOG_MODE``), ``cropduster.E010``
  (``CROPDUSTER_APP_LABEL`` is not ``"cropduster"``), ``cropduster.W001``
  (storage URLs match no configured Thumbor prefix) and ``cropduster.W002``
  (``CROPDUSTER_CREATE_THUMBS = False`` under a renderer that needs the files).

*Settings*

* New: ``CROPDUSTER_URL_RENDERER``, ``CROPDUSTER_THUMBOR``,
  ``CROPDUSTER_DIALOG_MODE``, ``CROPDUSTER_DEV_SERVER_URL``,
  ``CROPDUSTER_API_PERMISSION``, ``CROPDUSTER_LEGACY_CSRF_EXEMPT``,
  ``CROPDUSTER_REMOTE_IMAGE_FETCH``.
* ``cropduster.settings`` reads from ``django.conf.settings`` whenever an
  attribute is accessed through ``cropduster.conf.settings``. As a result,
  ``override_settings`` and runtime reconfiguration are honored.
  ``CROPDUSTER_APP_LABEL`` and ``CROPDUSTER_DB_PREFIX`` remain import-time
  constants because model ``Meta`` reads them.
* ``CROPDUSTER_APP_LABEL`` remains fixed at ``"cropduster"`` because the
  existing migrations hardcode that label. ``cropduster.E010`` reports any
  other value; otherwise those migrations cannot resolve the application.
  ``CROPDUSTER_DB_PREFIX`` still allows two installations to coexist.
* With ``CROPDUSTER_REMOTE_IMAGE_FETCH = False``, an image source named by
  an ``http(s)`` URL is rejected instead of retrieved on the server.
* ``CROPDUSTER_LEGACY_CSRF_EXEMPT`` defaults to ``True`` through 5.x. Setting
  it to ``False`` applies ``csrf_protect`` to the two legacy endpoints, which
  will be the default in 6.0.

*Deprecations*

* ``Size(retina=True)`` warns and has no effect. The key remains in the
  serialized format so saved size sets continue to round-trip. The option and
  serialized key will both be removed in 6.0. Declare a double-resolution size
  under ``auto`` instead.
* Bare ``THUMBOR_SERVER`` / ``THUMBOR_SECURITY_KEY`` / ``THUMBOR_MEDIA_URL``
  settings warn; put them in the ``CROPDUSTER_THUMBOR`` dict.
* ``Thumb.cache_safe_url`` delegates to ``Thumb.get_url()``.
* ``cropduster.forms.get_cropduster_field_on_model()`` warns; use
  ``cropduster.utils.fields.get_cropduster_field()``.
* ``cropduster.utils.paths.get_upload_foldername()`` wraps
  ``cropduster.services.paths.unique_upload_dir()``.
* ``Image.path`` is kept but deprecated; callers should use the field file
  directly.
* ``cropduster/static/cropduster/js/cropduster.js`` is a ``console.warn`` shim,
  and ``jsrender.js`` is empty. They remain only for asset pipelines that
  reference those paths. Both files and the ``.data('sizes')`` channel will be
  removed in 6.0.

*Removed*

* The 2011-era dialog stack: Jcrop 0.9.12, jQuery Form, ``jquery.class.js``,
  ``json2.js``, ``upload.js``, ``upload.css``, ``jquery.jcrop.css``,
  ``jcrop.gif``, ``arrows.png``, ``LICENSE.Jcrop.txt`` and the three unused
  widget images.
* ``CropDusterThumbField``, the unused ``image_storage`` hook,
  ``cropduster/compat.py`` (and ``curry``), the custom ``views/base.py``
  implementation, and every pre-4.2 Django branch.
* generic-plus no longer provides ``generic_plus.compat``.
  ``from generic_plus.compat import compat_rel, compat_rel_to`` raises
  ``ModuleNotFoundError``. Code that used these helpers should read
  ``field.remote_field`` and ``field.remote_field.model`` directly.
* generic-plus no longer depends on ``python-monkey-business``. Admin patches
  now use ``generic_plus.patching.patch``, which applies ``functools.wraps`` to
  the original method. Patched versions of ``ModelAdmin.__init__``,
  ``get_inline_instances`` and ``formfield_for_dbfield`` therefore report
  ``__module__ == 'django.contrib.admin.options'`` instead of
  ``'generic_plus.models'``. Code that previously checked the module name
  should check for ``_generic_plus_patched_original`` instead.
* ``python-xmp-toolkit`` is no longer a hard dependency. Standalone mode needs
  ``pip install django-cropduster[standalone]``, and thumbor URL signing needs
  ``[thumbor]``. Both are optional. The standalone route remains registered
  without its extra so that a missing dependency produces a configuration
  error instead of a 404.
* Python 3.9 and earlier, Django 4.1 and earlier.

*Bug fixes*

* ``GenericRelatedObjectManager.get_queryset()`` filters by
  ``field_identifier``, so ``instance.<field>_generic_rel.all()`` no longer
  returns rows belonging to a sibling field on the same model. The filter
  applies to any ``GenericForeignFileField`` subclass that sets a
  ``field_identifier``, including a project-defined video-upload field and
  models with several such fields.
* ``manager.clear()`` iterates the filtered ``all()``, so it deletes only the
  field's own rows. Under 3.1.0 it deleted every generic row for the instance,
  which could delete data belonging to the instance's other field identifiers.
  Code that intentionally used ``clear()`` to drop all of an instance's
  attachments must now clear each field explicitly.
* generic-plus's ``manager.add()`` and ``manager.create()`` now write
  ``FieldFile.name`` instead of requiring a ``path`` attribute on the related
  model; previously they raised ``AttributeError`` for a related model
  without ``path``. The value written by Cropduster is unchanged because
  ``Image.path`` already returned ``self.name``.
* Direct assignment to ``<field>_generic_rel`` raises ``TypeError``, as
  assignment to Django's own related managers has since Django 2.0. In the
  assignment branch this replaces, a multi-object assignment raised
  ``AttributeError`` on any storage, a single-object assignment raised
  ``NotImplementedError`` on storages without absolute paths (it read
  ``FieldFile.path``), and on local storage it wrote an absolute filesystem
  path into a column everything else treats as a storage-relative name; it
  was removed rather than repaired. Assign to the file field or use the
  manager's ``add()``, ``remove()`` and ``clear()`` methods.
* generic-plus appends an inline for a ``GenericForeignFileField`` only when
  the admin does not already have one. Version 3.1.0 used
  ``set(generic_file_fields) ^ set(existing_inline_fields)``. If an admin
  declared an inline for a ``GenericForeignFileField`` belonging to another
  model, the symmetric difference included that field and generic-plus appended
  a duplicate inline for it.
* The legacy crop view's ``CropForm.clean_sizes()`` returned ``None``, so
  ``crop.sizes`` was ``null``. It now returns the submitted sizes.
* A reference thumb with no crop box raised ``AttributeError`` while building a
  srcset.
* ``upload_to=None`` no longer produces a literal ``None/`` path segment.
* ``unique_upload_dir()`` checks storage with ``exists()`` instead of calling
  ``os.makedirs``, and clamps paths to the field's ``max_length``. This allows
  non-local storage and prevents long paths from overflowing the field.
* ``MetadataDict`` works on non-local storage, and gains ``from_string()``.
* Originals, previews and crops consistently use the storage declared by
  ``Image.image``; file-size lookup no longer assumes a local path.
* Temporary crop result names now refer to existing files. Standalone crops are
  not mislabeled as temporary, ``tmp=False`` does not copy an unchanged crop,
  and attaching to an unsaved object associates every generated thumb.
* ``ThumborRenderer`` keeps the crop operation for an offset box even when its
  dimensions equal the original image.
* CKEditor's OK button leaves the React iframe open while the dialog cannot
  commit. An active upload or crop therefore remains visible until its
  callback runs.
* A Python 2 ``.next()`` call was removed from
  ``cropduster/views/utils.py``.
* generic-plus fixed an ``isinstance``/``issubclass`` mix-up and a one-argument
  ``issubclass`` call.
* Previously unreachable widget-factory code now restores the factory's
  attributes.

*Behavior changes*

* ``CropDuster.complete()`` no longer calls ``CropDuster.setThumbnails()``. The
  formset writes are identical and occur in the same order. A project that
  monkey-patched the public method to observe completion no longer receives
  that call and should listen for ``cropduster:update`` instead.
* The widget's own writes to the formset dispatch ``input`` and ``change``,
  which 4.x did not do, so autosave, locking and change detection now see an
  upload. Set ``dispatchInputEvents: false`` in the widget's ``data-config`` to
  opt out.
* Because ``crop.sizes`` is no longer ``null``, the dialog rewrites
  ``#id_crop-sizes`` from a crop response where 4.15.0 skipped it. The value is
  the same list it was sent.
* Admin themes that restyled the old dialog's internals (``#crop_nav``,
  ``#current-thumb-info``, ``#error-container``) can no longer style those
  elements through selectors outside the shadow root. Those rules can be
  deleted.
* The dialog page no longer renders one ``thumbs-N-*`` table per size. The step
  count is available through ``#thumb-total-count``.
* ``attach()`` collects per-size rendering failures in ``AttachResult.errors``
  when ``permissive=True``. ``copy_image()`` defaults to ``permissive=False``
  and raises, matching the helper it replaces. Callers migrating from another
  helper should set ``permissive`` explicitly. With ``permissive=True``, the
  result may omit a required crop and report it only in
  ``AttachResult.errors``.
* ``GenericForeignFileField.formfield()`` now sets ``parent_admin``, ``request``
  and ``file_field_name`` on the widget instance. Previously, it set them before
  instantiating the widget. Passing a widget *class* to
  ``formfield(widget=...)`` therefore stored all three attributes on that class,
  and every field using the class read the values written by the last field.
  With several fields on one model, a widget could report another field's
  ``file_field_name``. The class also retained a live ``WSGIRequest`` for the
  lifetime of the worker process.
* The patched ``ModelAdmin.get_inline_instances()`` now calls
  ``get_fieldsets()`` only after it finds an inline that may need to be dropped.
  It previously made the call whenever it built inline instances for any admin.
  The returned inlines are unchanged, but the number and order of calls differ:
  across one project's admin registry, calls per pass dropped from 100 to 32.
  Side effects in ``get_fieldsets()`` or ``get_form()`` therefore run fewer
  times.
* The generic-plus widget now strips ``MEDIA_ROOT`` from the rendered
  ``file_value``. Version 3.1.0 built its pattern as
  ``r'^%s/?' % re.compile(MEDIA_ROOT)``, which interpolated the repr of the
  compiled pattern and never matched. As a result, the strip had not worked
  since roughly 1.x. A column containing
  ``/srv/example/media/podcasts/hero.mp4`` now renders as
  ``podcasts/hero.mp4``. The template writes ``file_value`` to the field's
  hidden input, so projects that store absolute paths will also post the
  stripped value. Storage-relative names, including the names written by
  Cropduster, are unchanged.
* The generic-plus widget context now includes ``field_identifier``,
  ``formset_prefix``, ``csrf_token``, ``config`` and ``config_json`` for the 5.0
  frontend. When the widget has a request, context construction calls
  ``django.middleware.csrf.get_token(request)``. Rendering the widget on an
  otherwise cacheable page therefore sets ``csrftoken`` and varies the response
  on ``Cookie``. Admin change forms already render ``{% csrf_token %}``, so
  their responses are unchanged.

**4.11.13 (Aug 2, 2018)**

* Fix Django 1.11 that prevented updating images in standalone mode
* Fix bug that threw exempi exceptions when uploaded images had iPhone face-recognition region metadata

**4.11.12 (Jul 3, 2018)**

* Fix Django 1.11 bug where newly uploaded images weren't named correctly.

**4.11.11 (Jun 6, 2018)**

* Support Django 2.0 and Django 2.1 alpha

**4.11.10 (Jun 6, 2018)**

* Fix Django 1.11 bug that prevented save of existing images

**4.11.9 (Mar 28, 2018)**

* Add ``skip_existing`` kwarg to ``generate_thumbs()`` method

**4.11.0 (Mar 12, 2017)**

* Add support for Django 1.10, drop support for Django < 1.8

**4.10.0 (July 26, 2015)**

* New: Add Image.alt_text field (requires a migration), which also gets returned now in the {% get_crop %} templatetag.
* Removed: ``exact_size`` argument for ``get_crop`` templatetag. Looking up exact
  sizes in the database and including the caption/attribution/alt_text is now the
  default behavior.

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
