Renderers
=========

A renderer converts a stored crop into its public URL. Cropduster includes two
renderers:

* ``FileRenderer`` returns URLs for derivative files written to storage.
* ``ThumborRenderer`` builds a Thumbor URL that crops the original on demand.

Pick one with ``CROPDUSTER_URL_RENDERER``::

    CROPDUSTER_URL_RENDERER = "cropduster.renderers.ThumborRenderer"

or, to pass constructor arguments::

    CROPDUSTER_URL_RENDERER = {
        "BACKEND": "cropduster.renderers.ThumborRenderer",
        "OPTIONS": {"server": "https://thumb.example.com/"},
    }

``OPTIONS`` are passed to the renderer's ``__init__``. The default is
``"cropduster.renderers.FileRenderer"``.

The API
-------

The following methods and template tags use the configured renderer:

``Thumb.get_url(*, image=None, multiplier=1, max_size=False, tmp=False, thumbs=None, **opts)``
    Returns this crop's URL, or ``None`` if it cannot be rendered.

``Thumb.get_srcset(*, densities=(1, 2), image=None, thumbs=None)``
    Returns a ``srcset`` attribute value, or ``None``.

``Image.get_url(size_name='original', **opts)``
    Returns an image rendition by name. ``'original'`` and ``'preview'`` are
    handled as they are in ``Image.get_file_for_size()``.

``BaseRenderer.preview_srcset(image, *, width, height)``
    Returns a higher-density candidate for a preview displayed at ``width`` by
    ``height``, or ``None``. The base implementation returns ``None``; only a
    renderer that can produce a larger preview on demand overrides it.

``{% get_crop image 'name' %}`` and ``{% get_thumbs image %}``
    Provide renderer URLs to template tags; see :doc:`quickstart`.

``Thumb.cache_safe_url`` is a deprecated alias for ``get_url()``.

A renderer may return ``None`` when a crop cannot be rendered. This occurs for
a legacy row without a crop box or when the crop is too small for the requested
pixel density. Templates should check for ``None``.

Pass ``image=`` when the ``Image`` has already been loaded. This saves a query
and is required to render an unsaved ``Thumb``. Pass ``thumbs=`` when the
image's other crops have already been loaded; ``FileRenderer`` uses them to
find density siblings.

Queries and prefetching
-----------------------

Rendering a bare ``Thumb`` reads its related ``Image`` from the database. A
``srcset`` also reads the image's sibling crops. Without prefetching, this
requires:

- **1 query per thumb** for ``get_url()``: dereferencing ``thumb.image``;
- **2 queries per thumb** for ``get_srcset()``: the same dereference plus
  ``image.thumbs.all()`` for the density sibling.

For querysets, prefetch the related objects instead of passing ``image=`` and
``thumbs=`` for each call::

    for image in Image.objects.with_thumbs().filter(...):
        for thumb in image.thumbs.all():
            thumb.get_srcset()

``Image.objects.with_thumbs()`` uses **2 queries in total**, regardless of the
number of images and crops returned. The reverse-FK prefetch populates
``thumb.image`` and provides each thumb's siblings. It also resolves
``reference_thumb``. An auto-sized crop reads its box from that related crop,
so without this prefetch ``get_crop_box()`` uses one additional query per auto
size.

The pieces are available separately:

``Thumb.objects.with_reference_thumbs()``
    Resolves ``reference_thumb`` from the queryset's own results for code that
    processes thumbs without their images. When ``reference_thumb`` is
    deferred, the method leaves it unresolved to avoid one query per row.

``prime_reference_thumbs(thumbs)``
    Performs the same operation on a list. ``{% get_crop %}`` and
    ``{% get_thumbs %}`` call it on ``image.thumbs.all()``. When those thumbs
    were prefetched, the template tags render them without additional queries.

Thumbor URLs use the original and the crop box, so they read the same model
rows. The query counts therefore apply to both renderers.

srcset and pixel density
------------------------

``multiplier=N`` requests an N× rendition and returns ``None`` if the source is
too small or no matching file exists::

    {% get_crop article.image 'lead' as img %}
    <img src="{{ img.url }}" srcset="{{ img.srcset }}">

``srcset()`` checks each value in ``densities`` and omits values that cannot be
rendered. If the 1× rendition cannot be rendered, the result is ``None``.

The renderers locate higher-density crops differently:

- **ThumborRenderer** multiplies the requested dimensions and does not upscale.
  It returns no N× rendition when the crop box is smaller than the requested
  output.
- **FileRenderer** has only the files that were written, so it looks for a
  *sibling crop* of the same image that is N times the size:
  ``find_density_sibling()``. It matches an exact ``<name>@<N>x`` first, then
  a sibling with exactly N× the dimensions. When multiple crops match, it
  prefers one made from the same crop box.

The crop dialog also requests a preview candidate from the renderer.
``ThumborRenderer`` returns only the ``<url> 2x`` candidate because the preview
URL supplies the 1x source. It returns that candidate when the original is at
least twice the displayed preview's width and height. ``FileRenderer`` returns
``None`` because Cropduster writes one preview file and does not invent another
filename.

FileRenderer
------------

``FileRenderer`` returns URLs for files written by Cropduster and can add a
cache buster derived from the crop's ``date_modified``.

``cache_buster`` option
    ``"mod"`` emits ``?mod=<timestamp>``, the format used by
    ``Thumb.cache_safe_url``. ``"legacy"`` emits the bare ``?<timestamp>``
    used by ``{% get_crop %}``. ``None`` emits no cache buster.

Without an explicit option, ``get_url()`` retains ``"mod"`` and the template
tags retain ``"legacy"``. Set one option explicitly to use the same format in
both APIs::

    CROPDUSTER_URL_RENDERER = {
        "BACKEND": "cropduster.renderers.FileRenderer",
        "OPTIONS": {"cache_buster": "mod"},   # ?mod=... from {% get_crop %} too
    }

``FileRenderer`` returns a storage URL unchanged when it already has a query
string. Signed storage backends put authentication fields in that query, and
changing it after signing would invalidate the signature.

``max_size=True`` returns the 1× URL because there is no separate maximum-size
file.

ThumborRenderer
---------------

Install the Thumbor extra::

    pip install django-cropduster[thumbor]

If ``libthumbor`` is unavailable, constructing the renderer raises
``ImproperlyConfigured`` with the name of the required extra. The
``manage.py check`` command reports this as ``cropduster.E001`` before a
template attempts to render a URL.

Every URL uses the original upload and its recorded crop box; no derivative
file is involved::

    CROPDUSTER_THUMBOR = {
        "SERVER": "https://thumb.example.com/",
        "MEDIA_URL": "https://cdn.example.com/media/",
        "SECURITY_KEY": "...",
        "EXTRA_MEDIA_URLS": [],
        "FILTERS": [],
        "SMART": False,
        "FIT_IN": False,
    }

``SERVER``
    The Thumbor server URL. This setting is required.
``MEDIA_URL``
    The prefix removed from a storage URL to produce the path resolved by the
    Thumbor loader (``media/...``). See below.
``SECURITY_KEY``
    The key URLs are signed with. Leave it unset to use ``/unsafe/`` URLs. A value other than
    a string, bytes or ``None`` raises ``ImproperlyConfigured`` and is reported
    as ``cropduster.E001``.
``EXTRA_MEDIA_URLS``
    Additional storage URL prefixes to remove. See below.
``FILTERS``, ``SMART``, ``FIT_IN``
    Passed to libthumbor for every URL. Individual calls can pass other
    libthumbor options as keyword arguments to ``get_url()``.

Cropduster reads ``THUMBOR_SERVER``, ``THUMBOR_MEDIA_URL`` and
``THUMBOR_SECURITY_KEY`` as fallbacks for ``SERVER``, ``MEDIA_URL`` and
``SECURITY_KEY``, respectively, and emits a ``DeprecationWarning``.

``max_size=True`` renders at the crop box's own resolution and omits the size
segment. ``tmp`` is ignored because Thumbor uses the original rather than a
temporary rendition.

The media URL and ``cropduster.W001``
`````````````````````````````````````

Cropduster removes the media prefix from a storage URL before signing it so
that a path such as ``media/<path>`` resolves to the same bytes in Thumbor. A
storage backend may use a host that does not appear in ``MEDIA_URL``, as S3
backends commonly do. Cropduster therefore tries
``CROPDUSTER_THUMBOR["MEDIA_URL"]``, ``settings.MEDIA_URL`` and each value in
``EXTRA_MEDIA_URLS``, in that order. It uses the first matching prefix. If none
matches, it passes the complete URL to Thumbor, which requires an HTTP loader.

Cropduster adds a trailing slash to each prefix and to ``SERVER`` when needed,
so ``https://cdn.example.com/media`` and
``https://cdn.example.com/media/`` are equivalent.

``cropduster.W001`` is reported when the storage URL does not begin with any
configured media prefix. In that case Cropduster passes the complete URL to
Thumbor, which requires an HTTP loader. A Thumbor installation without that
loader commonly returns a gateway timeout.

The check calls ``Image.image.storage.url()`` with a probe name and compares
the returned URL with the configured prefixes. This uses the URL produced by
the storage backend even when it differs from ``MEDIA_URL``. If the storage
backend cannot return a URL for the probe, the check emits no warning.

Metadata-only mode
------------------

With ``CROPDUSTER_CREATE_THUMBS = False``, Cropduster records crop boxes and
writes only the original. ``Crop``, ``Size.fit_to_crop()``,
``Size.fit_image()`` and ``Thumb.crop()`` accept a ``(width, height)`` pair in
place of a source image, so they can calculate crop geometry without opening a
file. ``cropduster.resizing.image_size()`` normalizes other supported inputs,
including a Pillow image, a storage path and a file field.
``Crop.create_image()`` raises ``CropDusterFileMissing`` when a caller attempts
to create a file from dimensions alone.

``BaseRenderer.supports_metadata_only`` indicates whether the renderer can
build a URL without a derivative file. ``cropduster.W002`` is reported when
thumbnail creation is disabled for a renderer that still requires those
files. Without that check, its crop URLs would refer to files that were not
written.
