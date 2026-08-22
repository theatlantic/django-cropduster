django-cropduster
=================

[![Test](https://github.com/theatlantic/django-cropduster/actions/workflows/test.yml/badge.svg)](https://github.com/theatlantic/django-cropduster/actions/workflows/test.yml)

<img alt="Cropduster logo" align="right" width="384" height="288" src="https://theatlantic.github.io/django-cropduster/cropduster-logo-monochrome.svg"/>

**django-cropduster** provides a Django model field and admin widget for
uploading an image and generating several named crops with predefined
dimensions and aspect ratios. It requires Python 3.10 or later, supports
Django 4.2 through 5.2, and depends on
[django-generic-plus](https://github.com/theatlantic/django-generic-plus) 4.x.
Developers at [The Atlantic](http://www.theatlantic.com/) created the project.

* [Installation](#installation)
* [Configuration](#configuration)
* [Documentation & Examples](#documentation--examples)
* [License](#license)
* [Development](#development)
* [Frontend development](#frontend-development)

Installation
------------

Install django-cropduster from
[PyPI](https://pypi.org/project/django-cropduster/):

        pip install django-cropduster

Standalone mode provides the WYSIWYG-editor dialog and stores crop geometry in
the image's XMP metadata. It requires the `standalone` extra and the `exempi`
shared library:

        pip install django-cropduster[standalone]

To serve crops from a [Thumbor](https://www.thumbor.org/) server instead of
writing derivative files, install the `thumbor` extra. See
[Renderers](https://django-cropduster.readthedocs.io/en/latest/renderers.html).

        pip install django-cropduster[thumbor]

To install a development checkout directly from GitHub:

        pip install -e git+https://github.com/theatlantic/django-cropduster.git#egg=django-cropduster

If the source is already checked out:

        pip install -e .

Configuration
-------------

Add `"cropduster"` to `INSTALLED_APPS` and include `cropduster.urls` in the
Django URL configuration.

```python
# settings.py

INSTALLED_APPS = [
    # ...
    'cropduster',
]

# urls.py

urlpatterns = [
    # ...
    path('cropduster/', include('cropduster.urls')),
]
```

This mounts both the 4.x formset endpoints and the JSON API used by the admin
widget (`cropduster/api/v1/`). Run `collectstatic` after upgrading because
the admin JavaScript is packaged as
`cropduster/dist/cropduster.js`.

Documentation & Examples
------------------------

    class Size(name, [label=None, w=None, h=None, auto=None,
        min_w=None, min_h=None, max_w=None, max_h=None, required=True])

Use `Size` to define each named crop. Set `auto` to a list of `Size` objects
that Cropduster should generate from the crop selected for the parent size.

`CropDusterField` accepts the arguments supported by Django's `ImageField`
and adds a `sizes` keyword containing a list of `Size` objects.

An example models.py:

```python
from cropduster.models import CropDusterField, Size

class ExampleModel(models.Model):
    MODEL_SIZES = [
        # Sizes selected explicitly by the editor.
        Size("large", w=210, auto=[
            # Sizes generated from the "large" crop.
            Size('larger', w=768),
            Size('medium', w=85, h=113),
            # More automatically generated sizes ...
        ]),
        # More editor-selected sizes ...
    ]

    image = CropDusterField(upload_to="your/path/goes/here", sizes=MODEL_SIZES)
```

Use the `get_crop` template tag to retrieve a crop in a template:

```django
{% load cropduster_tags %}

{% get_crop obj.image 'large' as img %}

{% if img %}
<figure>
    <img src="{{ img.url }}" srcset="{{ img.srcset }}"
         width="{{ img.width }}" height="{{ img.height }}"
         alt="{{ img.alt_text }}" />
    {% if img.attribution %}
    <figcaption>
        {{ img.caption }} (credit: {{ img.attribution }})
    </figcaption>
    {% endif %}
</figure>
{% endif %}
```

`CROPDUSTER_URL_RENDERER` names the backend that builds crop URLs.
`FileRenderer`, the default, writes derivative files and returns URLs from
the configured storage. `ThumborRenderer` builds URLs for a Thumbor server
instead. Python code can attach and crop images with `cropduster.attach()`.
See the
[documentation](https://django-cropduster.readthedocs.io/) for renderers, the
HTTP API, the programmatic API, and the 5.0 upgrade guide.

Development
-----------
Cropduster 5.0 depends on django-generic-plus 4.0. The test environments
install the version declared in `pyproject.toml` from PyPI.

[uv](https://docs.astral.sh/uv/) manages the demo project in `demo/` and the
Playwright suite in `e2e/`. The workspace installs the checked-out
django-cropduster package as editable and installs django-generic-plus from
the locked PyPI artifact.

License
-------
The Django code is licensed under the
[Simplified BSD License](http://opensource.org/licenses/BSD-2-Clause). View
the `LICENSE` file under the root directory for complete license and copyright
information.

The admin JavaScript bundle includes React, ReactDOM, react-image-crop, and
Scheduler. Vite writes their notices to
`cropduster/static/cropduster/dist/LICENSES.txt` during the build.

Frontend development
--------------------
The admin JavaScript is a TypeScript project in `frontend/`, built with
[Vite](https://vite.dev/) and managed with npm. It uses the Node version in
`frontend/.nvmrc` (Node 22). With [nvm](https://github.com/nvm-sh/nvm)
installed, run `nvm use` inside `frontend/` to select that version. `npm ci`
installs the versions recorded in `frontend/package-lock.json`. The
`typecheck`, `lint`, `test`, and `build` scripts run the checks used by CI.

`npm run build --prefix frontend` writes the bundle to
`cropduster/static/cropduster/dist/`. The built files are **committed to the
repository**, so installation does not require Node. After changing a file
under `frontend/`, rebuild and commit the resulting `dist/` files in the same
commit. CI rebuilds the bundle and fails if the committed files differ.

The committed source map makes production admin stack traces readable.
`scripts/check_dist.py` fails when the packaged map exceeds 2 MB, so the map
cannot dominate the wheel size.

Build the wheel and sdist with `python -m build`, then run
`python scripts/check_dist.py` to check their assets, metadata, long
description, and source-map size. Vitest compares the TypeScript crop geometry
with 2,114 vectors extracted from Cropduster 4.15.0 plus 13 explicit edge
cases. The extraction scripts are in `frontend/tests/legacy/`.
