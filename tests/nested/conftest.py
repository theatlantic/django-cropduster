"""
Collect these tests only under ``tests.settings_nested``.

django-nested-admin and the ``tests.nested`` application are installed only
by the ``nested`` tox environment. Importing these modules under the regular
settings would register models from an application that is not installed.
"""

from django.conf import settings


collect_ignore_glob = []

if 'tests.nested' not in settings.INSTALLED_APPS:
    collect_ignore_glob = ['*.py']
