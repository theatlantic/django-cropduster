from __future__ import unicode_literals

import os
import re

from django.core.files.storage import default_storage, FileSystemStorage
from django.conf import settings
from django.db.models.fields.files import FileField
from django.utils import six


__all__ = ('get_upload_foldername')


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
    parent_dir, _, basename = root_dir.rpartition('/')
    image_dir = ''
    i = 1
    dir_name = basename
    while not image_dir:
        try:
            sub_dirs, _ = default_storage.listdir(parent_dir)
            while dir_name in sub_dirs:
                dir_name = "%s-%d" % (basename, i)
                i += 1
        except OSError:
            os.makedirs(os.path.join(settings.MEDIA_ROOT, parent_dir))
        else:
            image_dir = os.path.join(parent_dir, dir_name)

    return image_dir
