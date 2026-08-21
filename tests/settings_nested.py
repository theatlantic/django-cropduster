"""
Settings for the django-nested-admin test environment.

The ``nested`` tox environment installs django-nested-admin and uses these
settings to add ``tests.nested``. Cropduster does not depend on
django-nested-admin outside this test environment.
"""

from .settings import *  # noqa: F401,F403
from .settings import INSTALLED_APPS


INSTALLED_APPS = INSTALLED_APPS + ('nested_admin', 'tests.nested')

ROOT_URLCONF = 'tests.urls_nested'
