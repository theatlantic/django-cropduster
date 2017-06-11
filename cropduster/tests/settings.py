import django
import dj_database_url

from django_admin_testutils.settings import *


if django.VERSION > (1, 11):
    MIGRATION_MODULES = {
        'auth': None,
        'contenttypes': None,
        'sessions': None,
        'cropduster': None,
    }

DATABASES['default'] = dj_database_url.parse(os.environ.get('DATABASE_URL', 'sqlite://:memory:'))

INSTALLED_APPS += (
    'generic_plus',
    'cropduster',
    'cropduster.tests',
)

ROOT_URLCONF = 'cropduster.tests.urls'

TEMPLATES[0]['OPTIONS']['debug'] = True
