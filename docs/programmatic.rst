Attaching images in code
========================

``attach()`` performs the same storage, crop, and model operations as the admin
dialog without requiring a browser request. It stores the source image, creates
each crop declared by the field, and returns an ``AttachResult`` containing the
resulting ``Image`` and ``Thumb`` objects::

    import cropduster

    result = cropduster.attach(article, "lead_image", "/tmp/photo.jpg")
    result.thumbs["main"].get_url()

``source`` may be a storage name, absolute local path, ``http(s)`` URL, Django
``File`` or ``UploadedFile``, Pillow image, or existing Cropduster ``Image``.
Cropduster copies or downloads other inputs into a separate image directory.
An existing Cropduster image already has a managed original and can be attached
without copying it.

``attach()``
------------

.. code-block:: python

    cropduster.attach(
        instance, field_name, source, *,
        sizes=None, metadata=None, crops=None, sources=None, upload_to=None,
        preview=True, commit=True, tmp=None, permissive=True,
        skip_existing=False)

``sizes``
    Sizes to crop. By default, Cropduster uses the field's sizes and resolves a
    callable against ``instance``.

``metadata``
    Values for ``attribution``, ``attribution_link``, ``caption``, and
    ``alt_text``.

``crops``
    Crop boxes by size name for sizes that should not use an automatically
    selected box. Each value may be a ``Box``, ``Thumb``, ``Crop``, or
    ``(x, y, w, h)`` tuple. The value identifies the source region;
    ``attach()`` still fits that region to the size's aspect ratio and output
    dimensions::

        cropduster.attach(article, "lead_image", photo,
                          crops={"main": (0, 0, 1600, 900)})

    A key that does not match a requested size raises ``ValueError`` so a
    misspelled size is not silently ignored. An ``auto`` size cannot be named
    because it follows its referenced parent size.

``permissive``
    When ``True``, stores per-size rendering failures in ``result.errors``
    instead of raising them. Failures for sizes declared ``required=False`` are
    stored regardless of this option. An input smaller than a required size
    raises ``ImageTooSmallError`` before any files or rows are written.

    ``attach()`` defaults to ``True``; ``copy_image()`` defaults to ``False``.
    With ``permissive=False``, a required size that cannot be rendered raises
    ``CropDusterResizeException`` instead of returning an image without that
    crop.

``commit``
    Save the instance and attach its image and crops. See
    `Unsaved objects`_ for the behavior when the instance has not been saved.

``sources``
    Reserved for per-crop source images. In 5.0, naming any source other than
    the image being attached raises ``NotImplementedError``.

Cropduster reads and writes the original, preview, and crops through the
storage configured on ``Image.image``. The programmatic entry points do not
accept a per-call storage because an ``Image`` row does not record one for
later reads.

The result::

    result.image     # the Image row
    result.thumbs    # {size name: Thumb}, auto sizes under their own names
    result.errors    # {size name: exception} for the sizes that failed
    result.warnings  # [{"code", "message"}]
    result.payload() # the dictionary returned by the v1 API

Copying between objects
-----------------------

``copy_image()`` attaches an existing Cropduster image to another object's
field. The target references the same original file instead of duplicating it,
and the source metadata is copied. For each target size, ``copy_image()`` fits
the size to the source image's existing crop boxes and selects the box with the
greatest intersection-over-union. This retains the closest available framing
when the two fields use different size names or aspect ratios::

    cropduster.copy_image(article.lead_image, pinned_item, "image")

``reuse=True`` updates the ``Image`` row already assigned to the target field
instead of creating a row and leaving the previous one orphaned.
``skip_existing=True`` keeps crops that have already been rendered.

``permissive`` defaults to **False**, unlike ``attach()``. See the
``permissive`` description above.

Choosing a crop
---------------

``choose_crop(image, size, *, candidates=None, hint=None, image_size=None)``
fits the requested size to each candidate crop and returns the candidate with
the greatest intersection-over-union. Pass ``hint`` to select a specific
``Crop``, ``Thumb``, ``Box``, ``(x, y, w, h)`` tuple, or named image crop
without comparing the candidates.

``thumb_for_size(image, size, *, best_crop=None, image_size=None)`` converts the
selected crop into an unsaved ``Thumb``, or returns ``None`` when the image
cannot satisfy the size. ``Image.best_thumb_for_size(size, *, hint=None)``
selects the crop and creates the thumb::

    thumb = image.best_thumb_for_size(Size("square", w=400, h=400))
    thumb = image.best_thumb_for_size(size, hint="portrait")

Neither function reads pixels. ``image_size=(w, h)`` supplies dimensions when
the source file is unavailable. This allows Cropduster to calculate crops when
``CROPDUSTER_CREATE_THUMBS = False``.

``crop_overlap(c1, c2)`` returns the intersection of two crops divided by their
union.

Unsaved objects
---------------

The generic relation cannot reference an object without a primary key. For an
unsaved instance, ``attach()`` renders crops under temporary filenames and
saves them as orphaned ``Thumb`` rows with no image. The dialog uses the same
state while a form is being edited. By default, ``tmp`` is ``True`` when the
instance has no primary key.

With ``commit=True`` (the default), ``attach()`` saves the instance and attaches
the image and crops. With ``commit=False``, the crops remain orphaned until the
form attaches them while saving the instance.

Filling in a widget from the server
-----------------------------------

Use orphaned crops when a server view needs to populate a widget without
opening the dialog. ``payload(legacy=True)`` returns the structure consumed by
``CropDuster.complete()``, so a view can populate a Cropduster field from
another article, an ISBN lookup, or an image service::

    def pinned_item_data(request, article_id):
        article = Article.objects.get(pk=article_id)
        item = PinnedItem()

        result = cropduster.copy_image(
            article.lead_image, item, "image", commit=False, tmp=True)
        result.orphan_thumbs()

        return JsonResponse({"image": result.payload(legacy=True)})

.. code-block:: javascript

    CropDuster.complete(prefix + "-image", data.image);

``orphan_thumbs()`` sets each crop's image to null until the form is saved. The
widget submits each crop by primary key. The formset then attaches the rows and
renames their temporary renditions to their permanent filenames.

The legacy payload also includes fields read directly by downstream widget
integrations::

    {"crop": {"image_id", "orig_image", "orig_w", "orig_h",
              "thumbs": {"<name>": {"id", "name", "width", "height", "url"}}},
     "thumbs": [],
     "initial": true,
     "preview_url", "preview_w", "preview_h",
     "attribution", "attribution_link", "caption", "alt_text"}

- Metadata is stored at the top level beside ``crop``. Downstream pages read
  these values and write them to ``<prefix>-0-attribution`` and
  ``<prefix>-0-alt_text``.
- ``preview_*`` describes the **first crop**, not the preview rendition. The
  widget displays this crop as its preview.
- The top-level ``thumbs`` field is retained for compatibility.
  ``CropDuster.complete()`` checks that it is an object but does not read its
  contents.

``tmp=True`` renders crops under the temporary filenames used by the dialog,
whether or not the instance has already been saved. Every payload URL refers
to a temporary file. With ``commit=True``, ``attach()`` attaches and renames the
crops before returning, so the payload refers to the permanent files instead.

Without ``legacy=True``, ``payload()`` returns the dictionary produced by
``build_payload()``. It contains the same image, preview, sizes, thumbs,
metadata, and warnings fields returned by the JSON API. ``sanitize=True``
passes crop names through ``sanitize_size_name()`` for template subscripting.
``renderer=`` overrides ``CROPDUSTER_URL_RENDERER`` for URLs in this payload.
