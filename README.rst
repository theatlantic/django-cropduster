django-cropduster
#################

**django-cropduster** provides a drop-in replacement for Django's
``ImageField`` that can generate multiple crops at predefined sizes and aspect
ratios. It was created by developers at `The
Atlantic <http://www.theatlantic.com/>`_. It is compatible with python
2.7 and 3.4, and Django versions 1.4 - 1.8.

Installation
============

The recommended way to install django-cropduster is from
`PyPI <https://pypi.python.org/pypi/django-cropduster>`_::

        pip install django-cropduster

Alternatively, one can install a development copy of django-cropduster
from source::

        pip install -e git+git://github.com/theatlantic/django-cropduster.git#egg=django-cropduster

If the source is already checked out, use setuptools::

        python setup.py develop

Configuration
=============

To enable django-cropduster, ``"cropduster"`` must be added to
``INSTALLED_APPS`` in settings.py and you must include
``cropduster.urls`` in your django urlpatterns.

::

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

License
=======

The django code is licensed under the `Simplified BSD
License <http://opensource.org/licenses/BSD-2-Clause>`_. View the
``LICENSE`` file under the root directory for complete license and
copyright information.

The admin JavaScript bundle includes React, ReactDOM, and react-image-crop.
Their license notices are in
``cropduster/static/cropduster/dist/LICENSES.txt``.
