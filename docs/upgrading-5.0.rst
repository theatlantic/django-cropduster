Upgrading to 5.0
================

Cropduster 5.0 replaces the admin frontend, adds a JSON API beside the legacy
endpoints, and adds URL-rendering and programmatic-attachment APIs. It does not
change the database schema or the formset names posted by the widget:

* **No migrations.** Neither Cropduster nor django-generic-plus adds one. The
  three tables remain the 4.x tables.
* **No change to the formset.** The widget still renders a hidden inline
  formset with standard ``{prefix}-N-field`` names, and still writes the same
  values in the same order. Everything that reads ``lead_image-0-thumbs`` or
  toggles ``lead_image-0-DELETE`` in a POST continues to work, including
  reversion, autosave, locking, and admin log entries. The behavior differs
  only when the file column stores an absolute path; see
  :ref:`behaviour-changes-worth-knowing-about`.
* **No change to the widget's DOM selectors.** ``.cropduster-form``,
  ``.cropduster-data-field``, ``.cropduster-images``, ``.thumbs`` and the rest
  are unchanged, so existing stylesheets and third-party admin JavaScript
  continue to select them.
* **One documented legacy response correction.** ``cropduster/upload/`` and
  ``cropduster/crop/`` keep the 4.15.0 requests, HTTP 200 errors, and CSRF
  exemption used by clients that construct those POSTs directly.
  ``crop.sizes`` now contains the posted size list instead of ``null``.

Upgrade by updating the two package versions, configuring a renderer if the
project uses Thumbor, and running ``collectstatic``. To roll back, restore the
previous package versions and run ``collectstatic`` again.

Requirements
------------

* Python 3.10+ and Django 4.2+.
* ``django-generic-plus>=4.0,<5``. Cropduster 5.0 uses the widget context added
  by django-generic-plus 4.0. Earlier versions do not provide the configuration
  required by the frontend.
* No Node. The release process builds the frontend from ``frontend/`` and
  commits the result, so the installed package includes
  ``cropduster/static/cropduster/dist/cropduster.js``.
* ``pip install django-cropduster[standalone]`` if you use the WYSIWYG dialog
  (``python-xmp-toolkit`` and the ``exempi`` library are no longer installed by
  default). Install ``[thumbor]`` when ``CROPDUSTER_URL_RENDERER`` uses
  ``ThumborRenderer``.

The upgrade, step by step
-------------------------

**1. Pin the two packages.**

::

    django-cropduster[standalone,thumbor]==5.0.0
    django-generic-plus>=4.0,<5

Then run ``collectstatic``. The package contains
``cropduster/dist/cropduster.js`` and ``cropduster/dist/cropduster.css`` under
fixed source names. Django's configured staticfiles storage processes those
files during collection, including adding hashes under
``ManifestStaticFilesStorage``. ``tests/test_staticfiles.py`` verifies both
assets with that storage.

**2. Point crop URLs at a renderer.**

No renderer setting is required when crops are served from the configured
storage. ``FileRenderer`` is the default and adds the 4.x ``?mod=`` cache
buster to query-free storage URLs. It leaves a storage URL unchanged when the
URL already has a query, which may contain a signature.

If you were building Thumbor URLs yourself, delete that code and configure
the renderer instead::

    CROPDUSTER_URL_RENDERER = "cropduster.renderers.ThumborRenderer"
    CROPDUSTER_THUMBOR = {
        "SERVER": "https://thumbor.example.com",
        "SECURITY_KEY": os.environ["THUMBOR_SECURITY_KEY"],
        "MEDIA_URL": "https://media.example.com/",
        # Every prefix your storage can emit URLs under. A URL that matches
        # none of them is passed to Thumbor whole; without an HTTP loader that
        # returns 504 for every image. cropduster.W001 reports it at check
        # time.
        "EXTRA_MEDIA_URLS": ["https://cdn.example.com/media/"],
    }

The existing ``THUMBOR_SERVER``/``THUMBOR_SECURITY_KEY``/``THUMBOR_MEDIA_URL``
settings continue to work and emit a warning, so they can be renamed in a
later change.

**3. Replace local template tags with the upstream ones.**

``{% get_crop %}`` now returns ``srcset`` alongside ``url``/``width``/
``height``, retains its ``"original"`` fallback, and uses the configured
renderer. A project with a local version of the tag can re-export Cropduster's
implementation for one release without changing every template::

    from cropduster.templatetags.cropduster_tags import get_crop  # noqa

The package also includes ``{% get_thumbs %}``, which returns crop entries
keyed by size name and stores the image fields under ``metadata``. For example,
``thumbs.main.url`` names a crop and ``thumbs.metadata.alt_text`` names the
image's alternative text.

**4. Delete local image utilities.**

Cropduster now includes replacements for local Thumbor URL builders,
``crop_overlap``-style crop selection, "fake image" wrappers that calculate
geometry without a file, and thumb generators. See :doc:`renderers` and
:doc:`programmatic`. In particular:

* ``cropduster.thumb_for_size(image, size, image_size=(w, h))`` renders one
  size, with or without a file on disk;
* ``cropduster.choose_crop()`` / ``Image.best_thumb_for_size()`` pick the
  closest existing crop;
* ``cropduster.copy_image()`` copies an image from one cropduster field to
  another, reusing crops that fit.

**5. Replace hand-built JSON payloads.**

Code that assembles crop data for a client, such as an editor autosave,
preview endpoint, or CMS API, can return the version 1 payload instead::

    result = cropduster.attach(article, "lead_image", upload)
    return JsonResponse(result.payload())          # v1 response fields
    return JsonResponse(result.payload(legacy=True))  # the 4.x shape

``payload(legacy=True)`` returns the exact 4.x crop-response structure,
including the retained top-level ``thumbs`` key. Existing consumers can process
it without changes.

**6. Update asset pipelines.**

Replace ``cropduster/js/upload.js``, Jcrop, ``jquery.form.js``,
``jquery.class.js``, ``json2.js``, and ``upload.css`` in asset bundles with
``cropduster/dist/cropduster.js`` and ``cropduster/dist/cropduster.css``
instead. The two no-op shims ``cropduster/js/cropduster.js`` and
``cropduster/js/jsrender.js`` remain available through 5.x, so an existing
pipeline that names them does not fail during ``collectstatic``. They are
removed in 6.0.

Rolling the dialog out in stages
--------------------------------

The dialog can render in an in-page modal, a full page, or the 4.x
``window.open`` popup. The presentation comes from ``CROPDUSTER_DIALOG_MODE``,
which defaults to ``"auto"``: modal when the viewport is at least 900x600, and
popup otherwise.

``"window"`` preserves the 4.x popup interaction and existing Selenium tests.
Use this rollout order:

#. staging on ``"window"``: verifies the new frontend with the existing
   interaction;
#. staging on ``"auto"``: verifies the modal behavior;
#. production on ``"window"`` for one week;
#. production on ``"auto"``.

During the rollout:

* A small iframe, including one with ``scrolling="no"``, may not fit the modal.
  ``"auto"`` checks the viewport and opens a popup instead. Forcing ``"modal"``
  can clip the dialog and make the crop button unreachable.
  ``CropDusterField(dialog_mode="window")`` selects the popup for one field.
* The modal retains the row from which it opened. Reordering a nested inline
  while the modal is open therefore writes the crop to the same row. In window
  mode, completion resolves the row from its prefix as it did in 4.x.

Rollback
--------

Restore the two previous package versions and run ``collectstatic``. There are
no migrations to reverse, and 4.15 can read the data written by 5.0 because
the JSON API writes the same rows as the legacy endpoints.

.. _behaviour-changes-worth-knowing-about:

Behavior changes worth knowing about
------------------------------------

``CropDuster.complete()`` no longer calls ``CropDuster.setThumbnails()``
    The widget writes the formset through
    ``FormsetBridge.writeComplete`` in the same order and with the same values
    as 4.x. It also rebuilds the thumb ``<select>`` through the bridge. The
    observable difference is that ``complete()`` no longer invokes the public
    ``CropDuster.setThumbnails()`` method. A project that patched this method
    to observe or change a completion must use another hook.
    ``setThumbnails()`` remains available and retains its behavior when called
    directly.

    Listen for ``cropduster:update`` instead. The event contains the same
    payload. A *jQuery* handler bound to ``document`` runs twice for each
    completion because Cropduster dispatches the event through two channels.
    The first call has no positional arguments.

The widget's writes dispatch ``input`` and ``change``
    Cropduster 4.x wrote hidden inputs with jQuery's ``.val()``, which did not
    dispatch browser events. Autosave, locking, and "you have unsaved changes"
    code therefore could not detect an upload. Version 5.0 uses the native
    setter and dispatches both events. Set ``dispatchInputEvents: false`` in
    the widget's ``data-config`` to suppress them for a form that cannot process
    these events.

The dialog uses ``cropduster/api/v1/``
    The 4.x formset endpoints (``cropduster/upload/`` and ``cropduster/crop/``)
    remain mounted and CSRF-exempt by default for clients that construct those
    POSTs directly. Their only response correction is ``crop.sizes`` as
    described above. The 5.0 widget does not call them. See :doc:`http_api`.

    The v1 ``state/``, ``upload/``, and ``crop/`` endpoints all require POST. A
    client that uses them must send ``X-CSRFToken`` and does not need to
    construct formset field names.

Payloads include renderer URLs and storage URLs
    ``thumbs[*].url`` contains the URL returned by
    ``CROPDUSTER_URL_RENDERER``. For a query-free storage URL, the default
    renderer includes a ``?mod=`` cache-busting parameter. A signed storage URL
    retains its existing query. ``ThumborRenderer`` may return a URL on another
    host. The adjacent ``file_url`` field contains the storage URL. The legacy
    completion payload has always returned the storage URL, and clients that
    parse storage filenames should continue to use ``file_url``.

``_generic_rel`` no longer leaks a sibling field's rows
    ``instance.<field>_generic_rel.all()`` did not filter by
    ``field_identifier``, so a model with more than one such field returned
    rows belonging to all of them. The relation now applies the filter. An
    additional downstream filter remains harmless. Code that needs images from
    the other field must query that field explicitly.

    This correction applies to every ``GenericForeignFileField`` subclass that
    sets a ``field_identifier``, not only Cropduster fields. For example, a
    project that defines a generic-plus video field gets the same filtered
    relation for that field.

``_generic_rel`` deletions are scoped to one field
    ``clear()`` now iterates the filtered ``all()``, so it deletes only rows
    belonging to that field. In django-generic-plus 3.1.0, it deleted every
    generic row attached to the instance, regardless of its identifier.

    This fixes data loss, but code that deliberately relied on the old behavior
    to remove all of an instance's attachments in one statement must now clear
    each field explicitly. This is the only behavior change in this release for
    which the same application operation can delete a different set of
    existing rows. Before upgrading, search for calls to
    ``*_generic_rel.clear()``.

Direct assignment to ``_generic_rel`` raises ``TypeError``
    ``instance.<field>_generic_rel = value`` is prohibited, as assignment to
    Django's own related managers has been since Django 2.0. Assign to the
    file field or use the manager's ``add()``, ``remove()`` and ``clear()``
    methods. No working code is affected: in the pre-4.0 assignment branch,
    a multi-object assignment raised ``AttributeError`` on any storage, a
    single-object assignment raised ``NotImplementedError`` on remote
    storages (it read ``FieldFile.path``), and on local storage it wrote an
    absolute filesystem path into a column everything else treats as a
    storage-relative name.

The widget strips ``MEDIA_ROOT`` from the file value it renders
    django-generic-plus 3.1.0 built the strip pattern as
    ``r'^%s/?' % re.compile(settings.MEDIA_ROOT)``. This interpolated the repr
    of the compiled pattern rather than the path, so the substitution did not
    match and had been a no-op since roughly 1.x. Version 4.0 now removes the
    prefix: a column containing
    ``/srv/example/media/podcasts/hero.mp4`` renders as
    ``podcasts/hero.mp4``.

    The widget template writes ``file_value`` to the hidden input named after
    the field. If the file column stores absolute paths, this changes both the
    rendered value and the value posted back. This is the exception to "no
    change to the formset" described above. Columns containing
    storage-relative names are unaffected; Cropduster itself writes names in
    that form.

Rendering a widget can set the CSRF cookie
    Cropduster 5.0 reads ``csrf_token`` from the widget context. When the
    widget has a request, django-generic-plus obtains that value by calling
    ``django.middleware.csrf.get_token(request)``, which marks the response as
    needing the CSRF cookie. A page that renders a generic-plus widget and was
    otherwise cacheable now returns ``csrftoken`` and varies on ``Cookie``.
    Admin change forms already emit ``{% csrf_token %}``, so their responses do
    not change.

``get_fieldsets()`` is called fewer times
    django-generic-plus patches ``ModelAdmin.get_inline_instances()`` so that
    it can drop a generic-plus inline whose field is absent from the fieldsets.
    Version 3.1.0 called ``get_fieldsets()`` on every admin during every pass.
    Version 4.0 waits until it encounters an inline that might need to be
    dropped, so an admin without a generic-plus inline does not call it. The
    same inlines are returned. In one project's registry, the call count per
    pass dropped from 100 to 32.

    This matters only when ``get_fieldsets()`` or the ``get_form()`` it invokes
    has a side effect, such as priming a cache, recording an audit row, or
    mutating ``self``. Those side effects now occur fewer times and at a
    different point in the request.

A custom widget's attributes are set on the instance, not the class
    Version 4.0 instantiates the widget before
    ``GenericForeignFileField.formfield()`` assigns ``parent_admin``,
    ``request``, and ``file_field_name``. Previously, when a field passed a
    widget *class* through ``formfield(widget=...)``, the method assigned all
    three attributes to the class. Fields sharing that class read whichever
    value was assigned most recently, and the class retained a live
    ``WSGIRequest`` for the lifetime of the worker. A widget subclass that
    reads any of these values as class attributes, whether at import time or
    from a ``classmethod``, must now read them from ``self``.

django-generic-plus internals were removed
    ``from generic_plus.compat import compat_rel, compat_rel_to`` now raises
    ``ModuleNotFoundError``. Read ``field.remote_field`` and
    ``field.remote_field.model`` instead. ``python-monkey-business`` is no
    longer a dependency. Its replacement uses ``functools.wraps``, so a
    patched admin method reports
    ``__module__ == 'django.contrib.admin.options'`` rather than
    ``'generic_plus.models'``. Code that identified the patch by module name
    should check for the ``_generic_plus_patched_original`` attribute instead.

    Version 4.0 also stops appending a duplicate inline for a
    ``GenericForeignFileField`` belonging to another model. The previous code
    used ``set(generic_file_fields) ^ set(existing_inline_fields)``. That
    symmetric difference included fields found only among the existing
    inlines, so it could select and append the foreign field again.

``crop.sizes`` in a legacy crop response is a list, not ``null``
    ``CropForm.clean_sizes()`` returned ``None`` in 4.x. The response now
    contains the posted sizes. The dialog therefore writes ``#id_crop-sizes``
    after a crop response; version 4.15.0 skipped that write. The value remains
    the same list sent in the request.

Admin themes no longer style the dialog's internals
    The dialog renders inside an open shadow root in both presentations. Theme
    rules for the old dialog under grappelli, including ``#crop_nav``,
    ``#current-thumb-info``, and ``#error-container``, no longer match and should
    be deleted. The widget button, thumbnails, and row remain in the light DOM
    and can still be styled.

``copy_image()`` raises where ``attach()`` collects
    ``attach()`` defaults to ``permissive=True`` and reports per-size failures
    in ``AttachResult.errors``; ``copy_image()`` defaults to
    ``permissive=False`` and raises, matching the previous copy helpers. Set
    ``permissive`` explicitly when replacing a local helper. With
    ``permissive=True``, the returned image may omit a required crop and report
    the failure only in ``AttachResult.errors``.

Appendix: a worked downstream migration
---------------------------------------

The following list applies the same upgrade to one downstream project's
module and setting names.

#. Pin ``django-cropduster==5.0.0`` and ``django-generic-plus>=4.0,<5`` with
   the ``[thumbor,standalone]`` extras, and regenerate the lock file.
#. ``CROPDUSTER_URL_RENDERER = "cropduster.renderers.ThumborRenderer"``; drop
   the project's own use-Thumbor flag; keep the existing ``THUMBOR_*``
   settings (they still work) and list the CDN prefix the storage emits in
   ``EXTRA_MEDIA_URLS``.
#. Replace the project's local copy of the template-tag module with a
   one-line re-export of Cropduster's tag for one release, leaving its 66
   templates alone, and delete its local ``get_thumbs``.
#. Delete the local Thumbor URL builders, ``crop_overlap``, the fake-image
   wrapper, the thumb generator, and the field-file import helper, and
   replace them with the Cropduster imports; keep the one standalone-image
   thumborizer Cropduster does not provide.
#. Replace the two views that build crop payloads by hand with
   ``AttachResult.payload(legacy=True)``; move the serializers onto
   ``thumb.get_url()``/``get_srcset()`` and ``Image.objects.with_thumbs()``.
#. Point the admin asset-pipeline bundle at
   ``cropduster/dist/cropduster.js``. The no-op shims keep the current bundle
   resolving until then, but the browser continues to request the duplicate
   assets.

Do not change the following as part of this upgrade: every
``-0-*`` POST-key reader, reversion, autosave, locking, ``LogEntry``, the
post-save admin signal, the downstream admin JavaScript, or the widget
selectors in the project's thirteen stylesheets. The dialog-internal rules in
the admin stylesheet can be deleted because they do not apply inside the
shadow root.

Use the same dialog rollout order: staging window, staging auto, production
window for one week, and production auto. The project's 830x550 admin iframe
selects the window presentation through ``"auto"`` and requires no per-field
setting.

The project's rich-text integration continues to post to the legacy
endpoints. Migrating it to ``api/v1/`` is separate work; that change can also
remove its client-side Thumbor URL builder and ``THUMBOR_SECURITY_KEY`` from
the browser.
