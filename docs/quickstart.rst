.. |cropduster| replace:: django-cropduster
.. |version| replace:: 4.8.18

.. _quickstart:

Quick start guide
=================

`Django <http://www.djangoproject.com>`_ version 1.4–1.8 needs to be installed to use django-cropduster. Installing cropduster should install its dependencies, `django-generic-plus <https://github.com/theatlantic/django-generic-plus>`_, `Pillow <https://python-pillow.github.io>`_, and `python-xmp-toolkit <http://python-xmp-toolkit.readthedocs.org>`_.

Installation
------------

.. code-block:: bash

    pip install django-cropduster

Go to https://github.com/theatlantic/django-cropduster if you need to download a package or clone/fork the repository.

Setup
-----

Open ``settings.py`` and add ``cropduster`` to your ``INSTALLED_APPS``

.. code-block:: python

    INSTALLED_APPS = (
        # ...
        'cropduster',
    )

Add URL-patterns:

.. code-block:: python

    urlpatterns = patterns('',
        # ...
        url(r'^cropduster/', include('cropduster.urls')),
    )

Collect the static files:

.. code-block:: bash

    $ python manage.py collectstatic

Example Usage
-------------

Model field
...........

``CropDusterField`` takes the same arguments as Django's ``ImageField``, as well as the additional keyword argument ``sizes``. The ``sizes`` should either be a list of ``cropduster.models.Size`` objects, or a callable that returns a list of ``Size`` objects.

.. code-block:: python

    from cropduster.models import CropDusterField, Size

    class ExampleModel(models.Model):

        image = CropDusterField(upload_to="some/path", sizes=[
            Size("main", w=1024, h=768, label="Main", auto=[
                    Size("square", w=1000, h=1000),
                    Size("main@2x", w=2048, h=1536, required=False),
                ]),
            Size("thumb", w=400, label="Thumbnail"),
            Size("freeform", label="Free-form")])

        second_image = CropDusterField(upload_to="some/path",
            field_identifier="second",
            sizes=[Size("100x100", w=100, h=100)])

Given the above model, the user will be prompted to make three crops after uploading an image for field ``image``: The first "main" crop would result in a 1024x768 image. It would also generate a 1000x1000 square image (which will be an optimal recropping based on the crop box the user created at the 4/3 aspect ratio) and, optionally, a "retina" crop ("main@2x") if the source image and user crop are large enough. The second "thumbnail" cropped image would have a width of 400 pixels and a variable height. The third "freeform" crop would permit the user to select any size crop whatsoever.

The field ``second_image`` passes the keyword argument ``field_identifier`` to ``CropDusterField``. If there is only one ``CropDusterField`` on a given model then the ``field_identifier`` argument is unnecessary (it defaults to ``""``). But if there is more than one ``CropDusterField``, ``field_identifier`` is a required field for the second, third, etc. fields. This is because it allows for a unique generic foreign key lookup to the cropduster image database table.

Admin Integration
.................

Adding the cropduster widget to the django admin requires no extra work. Simply ensure that the field is included in the ``ModelAdmin`` class.

Template usage
..............

To get a dictionary containing information about an image within a template, use the ``get_crop`` templatetag:

.. code-block:: django

    {% load cropduster_tags %}

    {% get_crop obj.image 'large' exact_size=1 as img %}

    {% if img %}
    <figure>
        <img src="{{ img.url }}" width="{{ img.width }}" height="{{ img.height }}"
             alt="{{ img.caption }}" />
        {% if img.attribution %}
        <figcaption>
            {{ img.caption }} (credit: {{ img.attribution }})
        </figcaption>
        {% endif %}
    </figure>
    {% endif %}

The ``exact_size`` keyword argument to the template tag is poorly named. If it is false (the default) then it will infer the url of the image based on the ``MEDIA_URL`` and the value of cropduster's FileField in the target model. It will also supply the width and height if they are explicitly defined in the size definition. It will not verify whether this information is accurate, or if the file for the crop in question even exists. In contrast, if ``exact_size`` is True, it will look up this information in the database via generic foreign key, and also pull in the image's caption and/or attribution.

Testing
-------

To run the unit tests:

.. code-block:: bash

    DJANGO_SELENIUM_TESTS=1 python manage.py test cropduster
