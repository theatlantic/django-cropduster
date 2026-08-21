"""Settings for a project without the ``standalone`` extra.

This removes the ``cropduster.standalone`` app and django-ckeditor from
:mod:`tests.settings`. The Cropduster plugin for django-ckeditor is the only
code that opens the standalone dialog. ``tests/test_noxmp.py`` uses
these settings, and the ``py312-dj52-noxmp`` tox environment runs it without
python-xmp-toolkit installed.
"""

from .settings import *  # noqa: F401,F403
from .settings import INSTALLED_APPS


WITHOUT_STANDALONE = ('cropduster.standalone', 'tests.standalone', 'ckeditor')

INSTALLED_APPS = tuple(app for app in INSTALLED_APPS if app not in WITHOUT_STANDALONE)

ROOT_URLCONF = 'tests.urls_noxmp'
