import os
import re
from datetime import datetime

from django.conf import settings
from django.template.defaultfilters import slugify


__all__ = ('get_upload_foldername', 'get_media_path', 'get_media_url',
    'get_relative_media_url')


MEDIA_ROOT = os.path.abspath(settings.MEDIA_ROOT)

re_media_root = re.compile(r'^%s' % re.escape(MEDIA_ROOT))
re_media_url = re.compile(r'^%s' % re.escape(settings.MEDIA_URL))
re_url_slashes = re.compile(r'(?:\A|(?<=/))/')
re_path_slashes = re.compile(r'(?<=/)/')


def get_available_name(dir_name, file_name):
    """
    Create a folder based on file_name and return it.

    If a folder with file_name already exists in the given path,
    create a folder with a unique sequential number at the end.
    """
    file_root, extension = os.path.splitext(file_name)
    file_root = slugify(file_root)
    name = os.path.join(dir_name, file_root)

    # If the filename already exists, keep adding a higher number
    # to the folder name until the generated folder doesn't exist.
    i = 2
    while os.path.exists(name):
        # file_ext includes the dot.
        name = os.path.join(dir_name, file_root + '-' + str(i))
        i += 1
    os.makedirs(name)

    return name


def get_upload_foldername(file_name, upload_to=None):
    # Generate date based path to put uploaded file.
    date_path = datetime.now().strftime('%Y/%m')

    paths = filter(None, [settings.MEDIA_ROOT, upload_to, date_path])
    upload_path = os.path.join(*paths)

    # Make sure upload_path exists.
    if not os.path.exists(upload_path):
        os.makedirs(upload_path)

    # Get available name and return.
    return get_available_name(upload_path, file_name)


def get_media_path(url):
    """Determine media URL's system file."""
    path = MEDIA_ROOT + '/' + re_media_url.sub('', url)
    return re_path_slashes.sub('', path)


def get_relative_media_url(path):
    """Determine system file's media URL without MEDIA_URL prepended."""
    url = re_media_root.sub('', path)
    return re_url_slashes.sub('', url)


def get_media_url(path):
    """Determine system file's media URL."""
    url = settings.MEDIA_URL + re_media_root.sub('', os.path.abspath(path))
    return re_path_slashes.sub('', url)
