import django

from selenosis.settings import *


if django.VERSION > (1, 11):
    MIGRATION_MODULES = {
        'auth': None,
        'contenttypes': None,
        'sessions': None,
        'cropduster': None,
    }

INSTALLED_APPS += (
    'generic_plus',
    'cropduster',
    'cropduster.tests',
)

ROOT_URLCONF = 'cropduster.tests.urls'

TEMPLATES[0]['OPTIONS']['debug'] = True
