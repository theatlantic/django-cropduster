django-cropduster
=================

[![Build Status](https://travis-ci.org/theatlantic/django-cropduster.svg?branch=v4)](https://travis-ci.org/theatlantic/django-cropduster)

<img alt="Cropduster logo" align="right" width="384" height="288" src="https://theatlantic.github.io/django-cropduster/cropduster-logo-monochrome.svg"/>

**django-cropduster** is a project that makes a form field available that
uses the [Jcrop jQuery plugin](https://github.com/tapmodo/Jcrop). It is a drop-in
replacement for django's `ImageField` and allows users to generate multiple crops
from images, using predefined sizes and aspect ratios. **django-cropduster**
was created by developers at [The Atlantic](http://www.theatlantic.com/).

**django-cropduster** is a mature library currently in production at
[The Atlantic](http://www.theatlantic.com/). However, the documentation at present is
far from adequate. Until there is sufficiently detailed documentation we
encourage any developers who have an interest in the project but are encountering
difficulties using it to create issues on the
[GitHub project page](https://github.com/theatlantic/django-cropduster) requesting
assistance.

* [Installation](#installation)
* [Configuration](#configuration)
* [Documentation & Examples](#documentation--examples)
* [License](#license)

Installation
------------

The recommended way to install django-cropduster is from [PyPI](https://pypi.python.org/pypi/django-cropduster):

        pip install django-cropduster

Alternatively, one can install a development copy of django-cropduster from source:

        pip install -e git+git://github.com/theatlantic/django-cropduster.git#egg=django-cropduster

If you are working from source, ensure that you have django-cropduster checked out to the `v4` branch. If
the source is already checked out, use setuptools:

        python setup.py develop

Configuration
-------------

To enable django-cropduster, `"cropduster"` must be added to `INSTALLED_APPS` in
settings.py and you must include `cropduster.urls` in your django urlpatterns.

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

    class Size(name, [label=None, w=None, h=None, retina=False, auto=None,
        min_w=None, min_h=None, max_w=None, max_h=None])

Use `Size` to create a crop with specified dimensions.  Use the `auto` parameter to setup other `Size` crops based on the container `Size`.



The `CropDusterField` is used much like the Django built in `ImageField`, but with the CropDuster `sizes` parameter, which accepts a `Size` object.
An example models.py:

```python
#models.py

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

    image = CropDusterField(u"Image", max_length=255, upload_to="your/path/goes/here",
        null=True, default="", sizes=MODEL_SIZES)
    # other fields ...
```

License
-------
The django code is licensed under the
[Simplified BSD License](http://opensource.org/licenses/BSD-2-Clause). View
the `LICENSE` file under the root directory for complete license and copyright
information.

The Jcrop jQuery library included is used under the
[MIT License](https://github.com/tapmodo/Jcrop/blob/master/MIT-LICENSE.txt).
