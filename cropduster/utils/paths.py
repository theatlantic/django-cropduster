from __future__ import unicode_literals

import os
import re

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

    root_dir = os.path.splitext(filename)[0]
    root_dir = dir_name = os.path.join(settings.MEDIA_ROOT, root_dir)
    i = 1
    while os.path.exists(dir_name):
        if six.PY2:
            dir_name = b'%s-%d' % (root_dir, i)
        else:
            dir_name = '%s-%d' % (root_dir, i)
        i += 1
    os.makedirs(dir_name)
    return dir_name
