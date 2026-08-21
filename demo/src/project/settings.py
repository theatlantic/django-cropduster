"""Settings for the django-cropduster demo project.

The Playwright e2e suite (``e2e/``) uses this project for its Django admin.
This is a development-only configuration: the secret key is a literal and
``DEBUG`` is always enabled.
"""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

SRC_DIR = Path(__file__).resolve().parent.parent
DEMO_DIR = SRC_DIR.parent
REPO_DIR = DEMO_DIR.parent

SECRET_KEY = "cropduster-demo-insecure-dev-only-key"
DEBUG = True
ALLOWED_HOSTS = ["*"]

# The beta proxy terminates TLS and forwards the original request scheme.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "nested_admin",
    "generic_plus",
    "cropduster",
    "project.example",
]

MIDDLEWARE = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "project.urls"
WSGI_APPLICATION = "project.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [SRC_DIR / "project" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "debug": True,
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                # cropduster/upload.html reads `{{ STATIC_URL }}` for its jQuery
                # <script> tags.
                "django.template.context_processors.static",
                "django.template.context_processors.media",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.environ.get("DEMO_DB_PATH") or str(DEMO_DIR / "db.sqlite3"),
    },
}

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = str(DEMO_DIR / "static")

# generic_plus.utils.get_relative_media_url calls str.startswith(MEDIA_ROOT),
# so MEDIA_ROOT has to be a string rather than a Path.
MEDIA_URL = "/media/"
MEDIA_ROOT = str(DEMO_DIR / "media")

AWS_STORAGE_BUCKET_NAME = os.environ.get("AWS_STORAGE_BUCKET_NAME")
AWS_LOCATION = os.environ.get("AWS_LOCATION", "").strip("/")

if AWS_STORAGE_BUCKET_NAME:
    if not AWS_LOCATION:
        raise ImproperlyConfigured(
            "AWS_LOCATION is required when AWS_STORAGE_BUCKET_NAME is set."
        )

    STORAGES = {
        "default": {"BACKEND": "storages.backends.s3.S3Storage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    }
    AWS_DEFAULT_ACL = None
    AWS_S3_REGION_NAME = os.environ.get("AWS_REGION", "us-east-1")
    AWS_S3_SIGNATURE_VERSION = "s3v4"

DEFAULT_AUTO_FIELD = "django.db.models.AutoField"

CROPDUSTER_CREATE_THUMBS = True
CROPDUSTER_DIALOG_MODE = os.environ.get("CROPDUSTER_DIALOG_MODE") or "auto"

# Allow `/tiny-iframe/` to embed the admin from the same origin.
X_FRAME_OPTIONS = "SAMEORIGIN"
