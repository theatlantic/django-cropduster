.. _how_it_works

How it Works
============

GenericForeignFileField
-----------------------

Nearly all of the functionality in cropduster comes from its django model field, :py:class:`CropDusterField <cropduster.fields.CropDusterField>`. A great deal of functionality, in turn, comes from the :py:class:`GenericForeignFileField <generic_plus.fields.GenericForeignFileField>` in the package `django-generic-plus`_. Put in simplest terms, django-generic-plus allows one to create django model fields that are a hybrid of a `FileField`_ and a reverse generic foreign key (similar to Django's `GenericRelation`_, except that the relationship is one-to-one rather than many-to-many). In some respects these fields act the same as a `FileField`_ (or, in the case of django-cropduster, an `ImageField`_), and when they are accessed from a model they have the same API as a `FieldFile`_. But, as part of their hybrid status, ``GenericForeignFileField`` fields also have functionality that allows relating a file to one or more fields in another model. In the case of django-cropduster, this model is :py:class:`cropduster.models.Image`. An example might be edifying. Let's begin with a simple model:

.. code-block:: python

    class Author(models.Model):
        name = models.CharField(max_length=255)
        headshot = CropDusterField(upload_to='img/authors', sizes=[Size("main")])

Assuming that we are dealing with an ``Author`` created in the Django admin, one would access the :py:class:`cropduster.Image <cropduster.models.Image>` instance using ``Author.headshot.related_object``:

.. code-block:: python

    >>> author = Author.objects.get(pk=1)
    >>> author.headshot
    <CropDusterImageFieldFile: img/authors/mark-twain/original.jpg>
    >>> author.headshot.path
    "/www/project/media/img/authors/mark-twain/original.jpg"
    >>> author.headshot.related_object
    <Image: /media/img/authors/mark-twain/original.jpg>

The accessor at ``author.headshot.related_object`` is basically equivalent to running the following python code:

.. code-block:: python

    try:
        Image.objects.get(
            content_type=ContentType.objects.get_for_model(author),
            object_id=author.pk,
            field_identifier='')
    except Image.DoesNotExist:
        return None

Creating an instance with a cropduster field outside of the Django admin requires the creation of an instance of :py:class:`cropduster.Image <cropduster.models.Image>` and a call to the ``generate_thumbs`` method:

.. code-block:: python

    from cropduster.models import Image

    author = Author.objects.create(
        name="Mark Twain",
        headshot="img/authors/mark-twain/original.jpg")
    author.save()

    image = Image.objects.create(
        content_object=author,
        field_identifier='',
        image=author.headshot.name)

    author.headshot.generate_thumbs()

.. note::

    Cropduster requires that images follow a certain path structure. Let's continue with the example above. Using the built-in Django `ImageField`_, uploading the file ``mark-twain.jpg`` would place it in ``img/authors/mark-twain.jpg`` (relative to the ``MEDIA_ROOT``). Because cropduster needs a place to put its thumbnails, it puts all images in a directory and saves the original image to ``original.%(ext)s`` in that folder. So the cropduster-compatible path for ``img/authors/mark-twain.jpg`` would be ``img/authors/mark-twain/original.jpg``. When a file is uploaded via the Django admin this file structure is created seamlessly, but it must be kept in mind when importing an image into cropduster from outside of the admin.

.. _FileField: https://docs.djangoproject.com/en/1.8/ref/models/fields/#filefield
.. _ImageField: https://docs.djangoproject.com/en/1.8/ref/models/fields/#django.db.models.ImageField
.. _GenericRelation: https://docs.djangoproject.com/en/1.8/ref/contrib/contenttypes/#django.contrib.contenttypes.fields.GenericRelation
.. _django-generic-plus: https://github.com/theatlantic/django-generic-plus
.. _FieldFile: https://docs.djangoproject.com/en/1.8/ref/models/fields/#django.db.models.fields.files.FieldFile