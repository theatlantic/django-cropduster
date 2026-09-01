import os
import re

from django.core.files.storage import FileSystemStorage, default_storage
from django.conf import settings
from django.db.models.fields.files import FileField



__all__ = ('get_upload_foldername')


def get_upload_foldername(file_name, upload_to='%Y/%m'):
    # Generate date based path to put uploaded file.
    file_field = FileField(upload_to=upload_to)
    if not file_name:
        file_name = 'no_name'
    filename = file_field.generate_filename(None, file_name)
    filename = re.sub(r'[_\-]+', '_', filename)

    root_dir = os.path.splitext(filename)[0]
    parent_dir, _, basename = root_dir.rpartition('/')

    if isinstance(default_storage, FileSystemStorage):
        # The preview and named crop files are written at paths derived
        # from this directory without Storage.get_available_name(), so two
        # uploads must never be given the same directory. os.makedirs()
        # reserves the name: a concurrent call for the same basename gets
        # FileExistsError and retries with the next suffix.
        i = 1
        dir_name = basename
        while True:
            image_dir = os.path.join(parent_dir, dir_name)
            try:
                os.makedirs(default_storage.path(image_dir))
            except FileExistsError:
                dir_name = "%s-%d" % (basename, i)
                i += 1
            else:
                return image_dir

    # Storages without local directories (e.g. S3) have no operation that
    # can reserve a name; the scan picks the first unused one.
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
