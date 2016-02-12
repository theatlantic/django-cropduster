#!/usr/bin/env python
import os
import tempfile
import warnings

warnings.simplefilter('default')

import django


current_dir = os.path.abspath(os.path.dirname(__file__))
temp_dir = tempfile.mkdtemp()


DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:'
    }
}
SECRET_KEY = 'z-i*xqqn)r0i7leak^#clq6y5j8&tfslp^a4duaywj2$**s*0_'

if django.VERSION >= (1, 8):
    TEMPLATES = [{
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(current_dir, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.contrib.auth.context_processors.auth',
                'django.template.context_processors.debug',
                'django.template.context_processors.i18n',
                'django.template.context_processors.media',
                'django.template.context_processors.static',
                'django.template.context_processors.tz',
                'django.template.context_processors.request',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    }]
else:
    TEMPLATE_DIRS = (
        os.path.join(current_dir, 'templates'),
    )
    TEMPLATE_LOADERS = (
        'django.template.loaders.filesystem.Loader',
        'django.template.loaders.app_directories.Loader',
    )
    TEMPLATE_CONTEXT_PROCESSORS = (
        'django.contrib.auth.context_processors.auth',
        'django.core.context_processors.debug',
        'django.core.context_processors.i18n',
        'django.core.context_processors.media',
        'django.core.context_processors.static',
        'django.core.context_processors.tz',
        'django.core.context_processors.request',
        'django.contrib.messages.context_processors.messages',
    )

try:
    import grappelli
except ImportError:
    INSTALLED_APPS = tuple([])
else:
    INSTALLED_APPS = tuple(['grappelli'])

INSTALLED_APPS += (
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.messages',
    'django.contrib.sessions',
    'django.contrib.sites',
    'django.contrib.staticfiles',
    'django.contrib.admin',
    'generic_plus',
    'cropduster',
)
MIDDLEWARE_CLASSES = (
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
)

if django.VERSION >= (1, 7):
    MIDDLEWARE_CLASSES += (
        'django.contrib.auth.middleware.SessionAuthenticationMiddleware', )

SITE_ID = 1
ROOT_URLCONF = 'cropduster.tests.urls'
MEDIA_ROOT = os.path.join(temp_dir, 'media')
MEDIA_URL = '/media/'
STATIC_URL = '/static/'
DEBUG_PROPAGATE_EXCEPTIONS = True
TEST_RUNNER = 'django.test.runner.DiscoverRunner' if django.VERSION >= (1, 6) else 'discover_runner.runner.DiscoverRunner'
