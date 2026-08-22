HTTP JSON API
=============

The crop dialog uses three POST endpoints under Cropduster's URL
configuration::

    urlpatterns += [path("cropduster/", include("cropduster.urls"))]

===================================  ======  ==================================
URL                                  Method  Name
===================================  ======  ==================================
``cropduster/api/v1/state/``         POST    ``cropduster-api-state``
``cropduster/api/v1/upload/``        POST    ``cropduster-api-upload``
``cropduster/api/v1/crop/``          POST    ``cropduster-api-crop``
===================================  ======  ==================================

Each endpoint returns the version 1 payload described below. All three require
a CSRF token and authorization through ``CROPDUSTER_API_PERMISSION``, omit
``X-Frame-Options`` so the dialog can run in an iframe, and disable caching.

The legacy formset endpoints (``cropduster/upload/`` and
``cropduster/crop/``) retain their existing request and response format
through 5.x. This includes returning errors with HTTP 200 because existing
clients construct those requests directly. New clients should use the JSON
API.

The payload
-----------

All three endpoints and ``AttachResult.payload()`` use the following version 1
structure::

    {
      "version": 1,
      "image": {"id", "name", "url", "width", "height",
                "field_identifier", "content_type_id", "object_id"},
      "preview": {"url", "width", "height", "file_url", "srcset"},
      "sizes": [<serialized Size>, ...],
      "thumbs": {"<size name>": {"id", "name", "width", "height",
                                 "crop": {"x", "y", "width", "height"} | null,
                                 "ref", "ref_id", "url", "srcset", "file_url",
                                 "tmp", "changed", "source"}},
      "metadata": {"attribution", "attribution_link", "caption", "alt_text"},
      "warnings": [{"code", "message"}, ...]
    }

The fields have the following meanings:

- ``image`` describes the original image. Each ``thumbs`` entry identifies its
  crop source independently through ``source``, which is null in 5.0.
- ``thumbs`` uses the **raw** size name as its key, including names such as
  ``main@2x``. Templates that need to subscript this mapping can normalize a
  name with ``cropduster.utils.sizes.sanitize_size_name()``.
- ``crop`` is null for an auto size. The ``ref`` field names the crop that the
  auto size follows.
- The configured ``CROPDUSTER_URL_RENDERER`` backend produces ``url`` and
  ``srcset``, so either value
  may contain a cache-busting parameter or a URL on another host. ``file_url``
  contains the storage URL used by the legacy completion payload and by
  clients that parse a storage filename from the URL. The same distinction
  applies to ``preview.url`` and ``preview.file_url``. ``preview.srcset`` is a
  ``<url> 2x`` candidate or null; ``preview.url`` remains the 1x source.
  ``ThumborRenderer`` returns the candidate only when the original is at least
  twice the preview's reported width and height. ``FileRenderer`` returns null
  rather than naming a preview file that Cropduster did not write.
- An entry with ``"id": null`` and no ``url`` contains a proposed crop box for a
  size that has not been cropped.
- ``tmp`` is true when the rendition uses its temporary filename pending form
  submission.
- ``version`` changes when an existing key changes meaning. Adding a key does
  not change the version.

``POST api/v1/state/``
----------------------

Send URL-encoded form data describing the image and crops that the dialog
should open.

============================  ==================================================
Parameter                     Meaning
============================  ==================================================
``image``                     The image, as a storage path, a ``MEDIA_URL``-based
                              path, or an ``http(s)`` URL to be downloaded.
``id``                        An ``Image`` primary key. An unknown id is treated
                              as no image rather than as an error.
``thumbs``                    Comma-separated crop primary keys to load instead
                              of the image's saved crops. The widget sends the
                              rows in its bound formset because those rows may
                              differ from the database while a form is being
                              edited.
``sizes``                     JSON list of serialized sizes.
``preview_size``              ``WxH`` bounding box for the preview.
``max_w``                     Cap the width the image may be cropped to;
                              ignored when the image is no wider than that
                              already.
``target``                    See `Targets`_.
``upload_to``                 Where a downloaded ``image`` URL is stored.
                              Ignored when ``target`` is given.
============================  ==================================================

If ``image`` and ``id`` identify different filenames, the endpoint treats the
image as a replacement. The response contains the row **without its primary
key** because replacing an image creates a row instead of overwriting the old
image's crops.

The endpoint creates the preview rendition when it is missing. A renderer that
reads the original on demand may set ``supports_metadata_only`` and return a
preview URL without that file. Under other renderers, a failed preview write
returns ``400 invalid_image`` instead of a URL for a missing file.

When ``image`` contains an ``http(s)`` URL, the server downloads and stores the
file. See `Remote images`_ for the security implications and the setting that
disables remote downloads.

``POST api/v1/upload/``
-----------------------

``multipart/form-data``.

============================  ==================================================
Field                         Meaning
============================  ==================================================
``image``                     The file. Required.
``sizes``                     JSON list of serialized sizes. The endpoint
                              rejects an image that is too small for them.
``for_size``                  Validate minimum dimensions against only the
                              named size instead of every size. This allows a
                              replacement source that satisfies one crop but
                              is too small for the others.
``upload_to``                 Directory pattern, ``FileField`` style. Ignored
                              when ``target`` is given.
``preview_width``,            Preview bounding box.
``preview_height``
``standalone``                Store the image in standalone mode.
``md5``                       When provided, the endpoint rejects the upload
                              unless the stored bytes have this hash.
``target``                    See `Targets`_.
============================  ==================================================

``POST api/v1/crop/``
---------------------

``application/json``::

    {
      "image": {"id": 12} | {"name": "...", "width": 1300, "height": 1016},
      "target": {...},
      "sizes": [<serialized Size>, ...],
      "standalone": false,
      "thumbs": {
        "main": {"id": 34, "crop": {"x": 0, "y": 0, "width": 1200, "height": 960},
                 "width": 600, "height": 480,
                 "changed": true, "tmp": false, "source": null}
      }
    }

Include one ``thumbs`` entry for each size to process. Omitted sizes are not
changed:

- When ``changed`` is true, the endpoint renders the crop again under a **new**
  row. The saved row remains unchanged until the form is saved.
- When ``changed`` is false and the entry includes a crop box and id, the
  endpoint copies the saved rendition to its temporary filename.
- When the entry has no crop box, the response contains a suggested crop box
  instead of a file.

Set ``tmp`` to true when the current session has already rendered the size.
This prevents the endpoint from overwriting that temporary file with the saved
rendition. Clients should retain the ``tmp`` value from the previous response.

``source`` identifies the image used for the crop. Null and the name of the
image being cropped both select that image, which is the only source supported
in 5.0. Any other value returns
``501 per_size_source_unsupported``. The field is included in version 1 so a
later release can add alternate sources without changing the payload
structure.

The endpoint writes renditions under temporary filenames. It does not attach
the image to an object; the form does that when it is saved.

Crop coordinates are validated before storage or model writes. ``x`` and
``y`` must be nonnegative, ``width`` and ``height`` must be positive, and a
box cannot extend beyond known image dimensions. ``changed: true`` requires a
box. A crop id must belong to this image and have the requested size name.

Targets
-------

Each endpoint accepts a ``target`` that identifies the field being edited::

    "target": {"content_type": "articles.article",
               "object_id": 41,
               "field_name": "lead_image"}

``object_id`` may be omitted or null when the object has not been saved.

When a request includes ``target``, Cropduster uses the field's configuration:

- The field supplies ``upload_to``, and Cropduster ignores a value sent by the
  client.
- The field supplies the sizes. Callable ``sizes`` receive the object being
  edited (``None`` for an unsaved object) and the image currently assigned to the
  field, exactly as they do when the widget resolves them.
- A client-supplied ``sizes`` list selects the field's sizes by name. Every
  name must be declared by the field, or the endpoint returns
  ``400 sizes_not_allowed``. Cropduster uses the field's geometry instead of
  geometry supplied by the client.

This prevents a client from lowering the field's minimum dimensions. Without a
target, the API continues to trust the supplied sizes for compatibility with
the 4.x endpoints and with objects that have not been saved.

Omitting ``target`` does not bypass this check for a saved image. When a request
includes an ``Image`` id, Cropduster derives its model field and applies the
same object permission. When a request includes only a stored filename,
Cropduster checks every saved owner before ``ImageFile`` can read, download, or
write the file. An explicit target that does not own the image returns
``400 target_mismatch``.

A saved ``Thumb`` id must belong to the requested image and size. When the crop
endpoint creates an orphaned thumb for an unsaved form, it records the thumb
id, image name, and size name in the current Django session. State and crop
requests accept that row only from the same session. File-backed mode also
requires the matching temporary rendition in that image's storage.

CSRF and what a request can make the server do
----------------------------------------------

All three endpoints require a CSRF token in the ``X-CSRFToken`` header. The
widget includes the token in ``data-config``, the dialog page renders one, and
the cookie provides it in either case.

The endpoints run the CSRF check directly so a failure can use the JSON
``403`` error envelope instead of the project's HTML CSRF failure page.

The legacy endpoints remain exempt from CSRF because existing clients submit
those formset requests without a token::

    CROPDUSTER_LEGACY_CSRF_EXEMPT = True   # the default through 5.x

.. warning::

   **This default changes in 6.0.** Set it to ``False`` after every client of
   ``cropduster/upload/`` and ``cropduster/crop/`` sends a token. This applies
   ``csrf_protect`` now, matching the 6.0 behavior. The setting is read on each
   request, so tests can change it to identify clients that still omit the
   token.

   Cropduster does not issue a deprecation warning while the default remains
   ``True``. Such a warning would occur on every installation, including those
   that cannot change the default until all legacy clients have been updated.

Remote images
~~~~~~~~~~~~~

The ``state`` endpoint creates a missing preview rendition unless the renderer
can build the preview from the original on demand. When ``image`` is an
``http(s)`` URL, the endpoint also **downloads that URL on the server** and
writes the response body to storage. These writes require a CSRF-protected
POST. The CSRF check prevents another site from submitting the request with an
editor's session, but an authorized client can still request any address the
server can reach.

The 4.x dialog performs the same download through ``cropduster/``, which
requires ``@login_required``. The version 1 endpoint also applies
``CROPDUSTER_API_PERMISSION``. Remote downloads stay enabled by default,
matching 4.x, and a setting disables them::

    CROPDUSTER_REMOTE_IMAGE_FETCH = False   # default: True

When the setting is ``False``, the JSON API rejects a URL with ``400 invalid``
and ``cropduster/`` returns its legacy JSON error object. The setting does not
affect stored images or file uploads; it applies only to the paste-a-URL step.
Disable it unless that step is used.

Permissions
-----------

::

    CROPDUSTER_API_PERMISSION = "cropduster.api.permissions.staff_and_object_perm"

The setting names a callable with the signature ``(request, target)``.
``target`` contains the request's target or ``None``. Raising
``PermissionDenied`` or returning exactly ``False`` rejects the request with
the JSON ``403 permission_denied`` response instead of a login redirect. The
callables included with Cropduster return ``None`` when permission is granted.

``staff_and_object_perm`` (the default)
    Requires an active staff member. When the request includes a target, the
    user must also have the model permission for editing it: ``change`` when
    the target includes an ``object_id``, and ``add`` when it does not.

``login_required_only``
    Requires any active, logged-in user. The 4.x endpoints apply this rule.

A custom callable can access ``target.model``, ``target.field``,
``target.instance``, ``target.sizes``, and ``target.upload_to``. Cropduster
resolves each value only when it is accessed, so a callable can reject a
request before loading its target.

Errors
------

Every failure uses the same error envelope and an HTTP status that matches the
failure::

    {"error": {"code": "image_too_small",
               "message": "Image must be at least 600x480 ...",
               "field": "image",
               "details": {"min": [600, 480], "actual": [400, 300]}}}

``code`` is stable and is the value clients should branch on. ``message`` is
intended for display. ``field`` and ``details`` are null when they do not apply.

=====  ================================  ======================================
Code   ``code``                          Raised by
=====  ================================  ======================================
400    ``invalid``                       A malformed or missing parameter;
                                         ``field`` identifies it.
400    ``image_too_small``               The upload is smaller than its sizes
                                         require. ``details`` contains ``min``
                                         and ``actual`` as ``[w, h]``.
400    ``invalid_image``                 The file is not a usable image.
400    ``resize_failed``                 The crop box is too small for the size
                                         it was drawn for.
400    ``unknown_size``                  A size name that was never declared.
400    ``sizes_not_allowed``             Sizes the target's field does not
                                         declare. ``details`` contains
                                         ``refused`` and ``allowed``.
400    ``unknown_model``,                The target identifies a model or
       ``unknown_field``                 Cropduster field that does not exist.
400    ``target_mismatch``               The saved image does not belong to
                                         the target field.
400    ``md5_mismatch``                  The stored bytes do not hash to the
                                         declared md5.
403    ``permission_denied``             ``CROPDUSTER_API_PERMISSION`` refused.
403    ``csrf_failed``                   Missing or bad CSRF token.
404    ``not_found``                     No such image or crop.
405    ``method_not_allowed``            Wrong HTTP method.
413    ``request_too_large``             The body is over
                                         ``DATA_UPLOAD_MAX_MEMORY_SIZE``.
501    ``per_size_source_unsupported``   A crop source other than the image
                                         being cropped.
501    ``standalone_unavailable``        Standalone mode without the
                                         ``standalone`` extra installed. The
                                         request is valid, but this server
                                         cannot process it. Install the extra
                                         with
                                         ``pip install django-cropduster[standalone]``.
500    ``server_error``                  An unhandled server error. The
                                         ``cropduster`` logger receives the
                                         traceback; the response omits it.
=====  ================================  ======================================
