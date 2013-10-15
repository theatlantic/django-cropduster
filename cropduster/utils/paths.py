import os
import re

from django.conf import settings
from django.db.models.fields.files import FileField


__all__ = ('get_upload_foldername', 'get_media_path', 'get_relative_media_url')


MEDIA_ROOT = os.path.abspath(settings.MEDIA_ROOT)

re_media_root = re.compile(r'^%s' % re.escape(MEDIA_ROOT))
re_media_url = re.compile(r'^%s' % re.escape(settings.MEDIA_URL))
re_url_slashes = re.compile(r'(?:\A|(?<=/))/')
re_path_slashes = re.compile(r'(?<=/)/')


def get_upload_foldername(file_name, upload_to='%Y/%m'):
    # Generate date based path to put uploaded file.
    file_field = FileField(upload_to=upload_to)
    if not file_name:
        file_name = 'no_name'
    filename = file_field.generate_filename(None, file_name)
    filename = re.sub(r'[_\-]+', '_', filename)
    root_dir = os.path.splitext(filename)[0]
    root_dir = dir_name = os.path.join(settings.MEDIA_ROOT, root_dir)
    i = 1
    while os.path.exists(dir_name):
        dir_name = u'%s-%d' % (root_dir, i)
        i += 1
    os.makedirs(dir_name)
    return dir_name


def get_media_path(url):
    """Determine media URL's system file."""
    path = MEDIA_ROOT + '/' + re_media_url.sub('', url)
    return re_path_slashes.sub('', path)


def get_relative_media_url(path, clean_slashes=True):
    """Determine system file's media URL without MEDIA_URL prepended."""
    if path.startswith(settings.MEDIA_URL):
        url = re_media_url.sub('', path)
    else:
        url = re_media_root.sub('', path)
    if clean_slashes:
        url = re_url_slashes.sub('', url)
    return url
