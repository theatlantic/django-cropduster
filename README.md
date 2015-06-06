django-cropduster
=================

[![Build Status](https://travis-ci.org/theatlantic/django-cropduster.svg?branch=master)](https://travis-ci.org/theatlantic/django-cropduster)

<img alt="Cropduster logo" align="right" width="384" height="288" src="https://theatlantic.github.io/django-cropduster/cropduster-logo-monochrome.svg"/>

**django-cropduster** is a project that makes a form field available that
uses the [Jcrop jQuery plugin](https://github.com/tapmodo/Jcrop). It is a drop-in
replacement for django's `ImageField` and allows users to generate multiple crops
from images, using predefined sizes and aspect ratios. **django-cropduster**
was created by developers at [The Atlantic](http://www.theatlantic.com/). It
is compatible with python 2.7 and 3.4, and Django versions 1.4 - 1.8.

* [Installation](#installation)
* [Configuration](#configuration)
* [Documentation & Examples](#documentation--examples)
* [License](#license)

Installation
------------

The recommended way to install django-cropduster is from [PyPI](https://pypi.python.org/pypi/django-cropduster):

        pip install django-cropduster

Alternatively, one can install a development copy of django-cropduster from
source:

        pip install -e git+git://github.com/theatlantic/django-cropduster.git#egg=django-cropduster

If the source is already checked out, use setuptools:

        python setup.py develop

Configuration
-------------

To enable django-cropduster, `"cropduster"` must be added to `INSTALLED_APPS`
in settings.py and you must include `cropduster.urls` in your django
urlpatterns.

```python
# settings.py

INSTALLED_APPS = (
    # ...
    'cropduster',
)

# urls.py

urlpatterns = patterns('',
    # ...
    url(r'^cropduster/', include('cropduster.urls')),
)
```

Documentation & Examples
------------------------

    class Size(name, [label=None, w=None, h=None, auto=None,
        min_w=None, min_h=None, max_w=None, max_h=None, required=True])

Use `Size` to define your crops. The `auto` parameter can be set to a list of
other `Size` objects that will be automatically generated based on the
user-selected crop of the parent `Size`.

`CropDusterField` accepts the same arguments as Django's built-in `ImageField`
but with an additional `sizes` keyword argument, which accepts a list of
`Size` objects.

An example models.py:

```python
from cropduster.models import CropDusterField, Size

class ExampleModel(models.Model):
    MODEL_SIZES = [
        # array of Size objects for initial crop
        Size("large", w=210, auto=[
            # array of Size objects auto cropped based on container Size
            Size('larger', w=768),
            Size('medium', w=85, h=113),
            # more sub Size objects ...
        ]),
        # more initial crop Size objects ...
    ]

    image = CropDusterField(upload_to="your/path/goes/here", sizes=MODEL_SIZES)
```

To get a dictionary containing information about an image within a template,
use the `get_crop` templatetag:

```django
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
```

License
-------
The django code is licensed under the
[Simplified BSD License](http://opensource.org/licenses/BSD-2-Clause). View
the `LICENSE` file under the root directory for complete license and copyright
information.

The Jcrop jQuery library included is used under the
[MIT License](https://github.com/tapmodo/Jcrop/blob/master/MIT-LICENSE.txt).
