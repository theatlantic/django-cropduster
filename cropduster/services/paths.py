import os
import posixpath
import re

from django.core.files.storage import FileSystemStorage
from django.db.models.fields.files import FileField

from cropduster.utils.storage import get_image_storage


__all__ = ('unique_upload_dir',)


def unique_upload_dir(name, upload_to, *, storage=None, max_length=None):
    """Return an unused directory for an upload and its renditions.

    The original, preview, and named renditions use fixed filenames such as
    ``original.jpg``, ``_preview.jpg``, and ``main.jpg``. They therefore share
    a directory named after the uploaded file. If that directory already
    exists, ``-1``, ``-2``, and so on are appended until the name is unused.

    ``upload_to`` accepts the same strftime patterns and callables as
    ``FileField``. When it is ``None``, however, the returned directory is
    at the storage root. ``FileField`` would convert ``None`` to the string
    ``"None"``; 4.x stored files there, but no caller depends on that path.

    When ``max_length`` is set, the directory name is shortened without
    removing its uniqueness suffix.

    The return value is relative to the storage. On filesystem storage the
    function creates the directory before returning it, which reserves the
    name for the caller. Storages without real directories retain the scan.
    """
    storage = storage or get_image_storage()

    file_field = FileField(upload_to=upload_to or '')
    filename = file_field.generate_filename(None, name or 'no_name')
    filename = re.sub(r'[_\-]+', '_', filename)

    root_dir = posixpath.splitext(filename)[0]
    parent_dir, _, basename = root_dir.rpartition('/')

    if isinstance(storage, FileSystemStorage):
        i = 0
        while True:
            dir_name = _clamp(parent_dir, basename, i, max_length)
            image_dir = posixpath.join(parent_dir, dir_name)
            try:
                os.makedirs(storage.path(image_dir))
            except FileExistsError:
                i += 1
            else:
                return image_dir

    taken = _taken_predicate(storage, parent_dir)

    i = 0
    while True:
        dir_name = _clamp(parent_dir, basename, i, max_length)
        if not taken(dir_name):
            return posixpath.join(parent_dir, dir_name)
        i += 1


def _clamp(parent_dir, basename, index, max_length):
    """Append the uniqueness suffix and trim the name to ``max_length``.

    Only ``basename`` is shortened; a name trimmed into its suffix could
    collide with an existing directory.
    """
    suffix = '' if not index else '-%d' % index
    if max_length is None:
        return basename + suffix
    over = len(posixpath.join(parent_dir, basename + suffix)) - max_length
    if over > 0:
        basename = basename[:max(len(basename) - over, 1)]
    return basename + suffix


def _taken_predicate(storage, parent_dir):
    """Return a function that checks names below ``parent_dir``.

    On object storage, ``exists()`` may return false for a directory prefix
    even when objects exist below it. ``listdir()`` finds those prefixes.
    When a backend does not implement ``listdir()``, the check falls back to
    ``exists()``, and a missing parent is treated as empty.
    """
    try:
        sub_dirs = set(storage.listdir(parent_dir)[0])
    except NotImplementedError:
        return lambda dir_name: storage.exists(posixpath.join(parent_dir, dir_name))
    except OSError:
        return lambda dir_name: False
    return lambda dir_name: dir_name in sub_dirs
