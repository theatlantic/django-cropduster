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
            Size("large", w=1024, h=768, label="Large", auto=[
                    Size("large@2x", w=2048, h=1536, required=False),
                    Size("square", w=1000, h=1000),
                ]),
            Size("thumb", w=400, label="Thumbnail")])

Given the above model, the user will be prompted to make two crops after uploading an image: The first "large" crop would result in a 1024x768 image. It would also optionally generate a "retina" crop of twice those dimensions if the source image is large enough, and a 1000x1000 square image (which will be an optimal recropping based on the crop box the user created at the 4/3 aspect ratio). The second "thumbnail" cropped image would have a width of 400 pixels and a variable height.

Exposing the cropduster widget in your admin happens automatically with a ``ModelAdmin`` class.

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

The ``exact_size`` keyword argument to the template tag is poorly named. If it is false (the default) then it will infer the url of the image based on the ``MEDIA_URL`` and the value of cropduster's FileField in the target model. It will also supply the width and height if they are explicitly defined in the size definition. It will not verify whether this information is accurate, or if the crop in question even exists. In contrast, if ``exact_size`` is True, it will look up this information via generic foreign key, and also pull in the image's caption and/or attribution.

Testing
-------

To run the unit tests:

.. code-block:: bash

    DJANGO_SELENIUM_TESTS=1 python manage.py test cropduster
