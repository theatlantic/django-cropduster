.. |cropduster| replace:: django-cropduster

.. _quickstart:

Quick start guide
=================

django-cropduster requires Python 3.10 or later and Django 4.2 or later.
Installation also installs
`django-generic-plus <https://github.com/theatlantic/django-generic-plus>`_
and `Pillow <https://python-pillow.github.io>`_.

Installation
------------

.. code-block:: bash

    pip install django-cropduster

Standalone mode and Thumbor rendering use separate optional dependencies. The
WYSIWYG (standalone) dialog stores crop geometry in the image's XMP metadata
and requires
`python-xmp-toolkit <http://python-xmp-toolkit.readthedocs.org>`_ and the
``exempi`` shared library. Serving crops from a Thumbor server requires
``libthumbor``:

.. code-block:: bash

    pip install django-cropduster[standalone]
    pip install django-cropduster[thumbor]

The source repository is available at
https://github.com/theatlantic/django-cropduster.

Setup
-----

Add ``cropduster`` to ``INSTALLED_APPS`` in ``settings.py``:

.. code-block:: python

    INSTALLED_APPS = [
        # ...
        'cropduster',
    ]

Include the Cropduster URL patterns:

.. code-block:: python

    urlpatterns = [
        # ...
        path('cropduster/', include('cropduster.urls')),
    ]

This mounts the crop dialog endpoints and their JSON API; see :doc:`http_api`.

Collect the static files:

.. code-block:: bash

    $ python manage.py collectstatic

The package includes the built JavaScript and CSS, so installation does not
require a frontend build. ``collectstatic`` processes their fixed source names
through the configured staticfiles storage.

Example Usage
-------------

Model field
...........

``CropDusterField`` accepts the same arguments as Django's ``ImageField`` plus
the ``sizes`` keyword argument. ``sizes`` may be a list of
``cropduster.models.Size`` objects or a callable that returns such a list.

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

For the ``image`` field above, the dialog requests three crops. The ``main``
crop produces a 1024x768 image; from its selected 4:3 crop box Cropduster
also renders a 1000x1000 square and, when the source image and selected crop
are large enough, the optional ``main@2x`` rendition. The ``thumb`` crop is
400 pixels wide with a variable height. The ``freeform`` crop allows any
dimensions.

``field_identifier`` distinguishes multiple ``CropDusterField`` instances on
the same model when Cropduster resolves their generic foreign keys. A model's
first Cropduster field defaults to ``""``. Each additional field requires a
unique value, as shown by ``second_image`` above.

Admin Integration
.................

The Cropduster widget needs no additional Django admin configuration. Include
the field in the ``ModelAdmin`` class.

Template usage
..............

Use the ``get_crop`` template tag to retrieve one crop:

.. code-block:: django

    {% load cropduster_tags %}

    {% get_crop obj.image 'large' as img %}

    {% if img %}
    <figure>
        <img src="{{ img.url }}" srcset="{{ img.srcset }}" alt="{{ img.alt_text }}"
             width="{{ img.width }}" height="{{ img.height }}" />
        {% if img.attribution %}
        <figcaption>
            {{ img.caption }} (credit: {{ img.attribution }})
        </figcaption>
        {% endif %}
    </figure>
    {% endif %}

``img`` also contains ``thumb`` (the ``Thumb`` itself) and ``crop`` (its crop
box, or ``None``). ``url`` and ``srcset`` come from the configured renderer
and are ``None`` when the crop cannot be rendered; see :doc:`renderers`.

Use ``get_thumbs`` to retrieve every crop for an image:

.. code-block:: django

    {% get_thumbs obj.image as thumbs %}

    <img src="{{ thumbs.large.url }}" srcset="{{ thumbs.large.srcset }}">

Each crop entry has the same fields returned by ``get_crop``. Crop names are
sanitized for template lookup, so ``large@2x`` is available as ``large_2x``.
``SizeAlias`` entries from the field are then added to the result. The
``thumbs.metadata`` entry contains ``attribution``, ``attribution_link``,
``caption``, and ``alt_text``.

Testing
-------

From a checkout, the suite runs under tox across the supported Python and
Django versions:

.. code-block:: bash

    tox
    tox -e py312-dj52-nogrp -- --selenosis-driver=chrome-headless   # one env, browser tests included

The browser tests use Chrome through Selenium; ``--selenosis-driver`` selects
the browser. The frontend suites run under ``frontend/``: ``npm test`` runs
Vitest, and ``npm run test:e2e`` runs Playwright.
