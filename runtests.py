#!/usr/bin/env python
import django
import os
import sys
from django.core.management import execute_from_command_line

from django.conf import settings, global_settings as default_settings


current_dir = os.path.abspath(os.path.dirname(__file__))
test_dir = os.path.join(current_dir, 'test')


sys.path.insert(0, test_dir)

# Give feedback on used versions
sys.stderr.write('Using Python version %s from %s\n' % (sys.version[:5], sys.executable))
sys.stderr.write('Using Django version %s from %s\n' % (
    django.get_version(),
    os.path.dirname(os.path.abspath(django.__file__))))

if not settings.configured:
    settings.configure(**{
        'DEBUG': True,
        'TEMPLATE_DEBUG': True,
        'DATABASES': {
            'default': {
                'ENGINE': 'django.db.backends.sqlite3',
                'NAME': ':memory:'
            }
        },
        'TEMPLATE_LOADERS': (
            'django.template.loaders.app_directories.Loader',
        ),
        'TEMPLATE_CONTEXT_PROCESSORS': default_settings.TEMPLATE_CONTEXT_PROCESSORS + (
            'django.core.context_processors.request',
        ),
        'TEST_RUNNER': 'django.test.runner.DiscoverRunner' if django.VERSION >= (1, 6) else 'discover_runner.runner.DiscoverRunner',
        'INSTALLED_APPS': (
            'grappelli',
            'django.contrib.auth',
            'django.contrib.contenttypes',
            'django.contrib.messages',
            'django.contrib.sessions',
            'django.contrib.sites',
            'django.contrib.staticfiles',
            'django.contrib.admin',
            'generic_plus',
            'cropduster',
            'cropduster.tests',
            'testapp',
        ),
        'MIDDLEWARE_CLASSES': (
            'django.contrib.sessions.middleware.SessionMiddleware',
            'django.contrib.auth.middleware.AuthenticationMiddleware',
            'django.contrib.messages.middleware.MessageMiddleware',
        ),
        'SITE_ID': 1,
        'ROOT_URLCONF': 'testapp.urls',
        'MEDIA_ROOT': os.path.join(test_dir, 'media'),
        'MEDIA_URL': '/media/',
        'STATIC_URL': '/static/',
        'DEBUG_PROPAGATE_EXCEPTIONS': True,
    })


def runtests():
    argv = sys.argv[:1] + ['test', 'cropduster', '--traceback', '--verbosity=1'] + sys.argv[1:]
    execute_from_command_line(argv)

if __name__ == '__main__':
    runtests()
