django-cropduster
=================

**django-cropduster** is a project that makes available a form field available that
use the [Jcrop jQuery plugin](https://github.com/tapmodo/Jcrop). It is a drop-in
replacement for django's `ImageField` and allows users to generate multiple crops
from images using predefined sizes and aspect ratios. **django-cropduster** was created by developers at [The Atlantic](http://www.theatlantic.com/).

* [Installation](#installation)
* [Configuration](#configuration)
* [License](#license)

Installation
------------

The recommended way to install with pip from source:

        pip install -e git+git://github.com/theatlantic/django-cropduster.git#egg=django-cropduster

If the source is already checked out, use setuptools:

        python setup.py develop

Configuration
-------------

To enable django-cropduster, `"cropduster"` must be added to INSTALLED_APPS in
settings.py and adding `cropduster.urls` to your django urls.

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

License
-------
The django code is licensed under the
[Simplified BSD License](http://opensource.org/licenses/BSD-2-Clause). View
the `LICENSE` file under the root directory for complete license and copyright
information.

The Jcrop jQuery library included is used under the
[MIT License](https://github.com/tapmodo/Jcrop/blob/master/MIT-LICENSE.txt).
