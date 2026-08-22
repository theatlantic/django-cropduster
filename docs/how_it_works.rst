.. _how_it_works:

How it works
============

``CropDusterField`` is a ``GenericForeignFileField`` from
`django-generic-plus <https://github.com/theatlantic/django-generic-plus>`_.
The field presents an ``ImageField``-like value on the owning model while its
metadata and crops are stored in Cropduster's own rows.

For this model::

    class Author(models.Model):
        name = models.CharField(max_length=255)
        headshot = CropDusterField(
            upload_to="img/authors",
            sizes=[Size("main", w=600, h=480)],
        )

``author.headshot`` is a field-file proxy. Its ``related_object`` is the
corresponding ``cropduster.Image``::

    >>> author.headshot.name
    'img/authors/mark-twain/original.jpg'
    >>> author.headshot.related_object
    <Image: /media/img/authors/mark-twain/original.jpg>

The ``Image`` row points back to the owner through a content type, object id,
and ``field_identifier``. The identifier is empty for the first Cropduster
field on a model and distinguishes additional fields. Each rendered crop is a
``Thumb`` related to that ``Image``; an automatically generated size points at
the crop it follows through ``reference_thumb``.

Files and renderers
-------------------

Cropduster stores each uploaded image in a separate directory. The original is
stored as ``original.<ext>``, the crop-dialog preview as ``_preview.<ext>``,
and each file-backed crop under its size name. Temporary renditions add
``_tmp`` until the form saves them. All reads and writes use the storage
declared by ``Image.image`` rather than assuming a local filesystem.

The stored name is separate from the URL returned to a template.
``FileRenderer`` returns URLs for the derivative files; ``ThumborRenderer``
builds a URL from the original and recorded crop box. See :doc:`renderers`.

Creating images outside the admin
---------------------------------

Use :func:`cropduster.attach` instead of constructing ``Image`` and ``Thumb``
rows or reproducing Cropduster's directory layout by hand::

    import cropduster

    result = cropduster.attach(author, "headshot", "/tmp/mark-twain.jpg")
    result.thumbs["main"].get_url()

``attach()`` accepts storage names, local paths, URLs, Django files, PIL
images, and existing Cropduster images. It resolves the field's declared
sizes, writes the preview and crops, and associates the rows with the owning
object. Unsaved objects, custom crop boxes, copying between fields, and the
return value are covered in :doc:`programmatic`.
