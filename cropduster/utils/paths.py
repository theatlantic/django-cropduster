from __future__ import unicode_literals

import os
import re

from django.core.files.storage import default_storage, FileSystemStorage
from django.conf import settings
from django.db.models.fields.files import FileField
from django.utils import six


__all__ = ('get_upload_foldername')


MEDIA_ROOT = os.path.abspath(settings.MEDIA_ROOT)


def get_upload_foldername(file_name, upload_to='%Y/%m'):
    # Generate date based path to put uploaded file.
    file_field = FileField(upload_to=upload_to)
    if not file_name:
        file_name = 'no_name'
    filename = file_field.generate_filename(None, file_name)
    filename = re.sub(r'[_\-]+', '_', filename)

    if six.PY2 and isinstance(filename, unicode):
        filename = filename.encode('utf-8')

    image_dir = os.path.splitext(filename)[0]

    if default_storage.__class__ == FileSystemStorage:
        root_dir = os.path.join(settings.MEDIA_ROOT, image_dir)
        dir_name = default_storage.get_available_name(root_dir, max_length=255)
        image_dir = dir_name.replace(settings.MEDIA_ROOT + '/', '')
        os.makedirs(dir_name)

    return image_dir
