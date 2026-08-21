from __future__ import division

import os
import re
import hashlib

from django.core.exceptions import SuspiciousOperation
from django.core.files.images import get_image_dimensions
from django.core.files.uploadedfile import SimpleUploadedFile
from django.conf import settings
from django.db.models.fields.files import FieldFile, FileField
from django.utils.functional import cached_property
from urllib.parse import urlparse, unquote_plus
from urllib.request import urlopen

from generic_plus.utils import get_relative_media_url

from cropduster.conf import settings as cropduster_settings
from cropduster.utils.storage import get_image_storage


REMOTE_FETCH_REFUSED = (
    'Fetching an image from a URL is disabled. Set '
    'CROPDUSTER_REMOTE_IMAGE_FETCH to True to allow %s to be downloaded, '
    'or name an image that is already in storage.')

REMOTE_IMAGE_RE = re.compile(r'^https?://')


def normalize_stored_image_name(path):
    """Return a storage-relative image name, or ``None`` for a remote URL."""
    if not path:
        return None
    if '%' in path:
        path = unquote_plus(path)
    if path.startswith(settings.MEDIA_URL):
        return get_relative_media_url(path, clean_slashes=False)
    if REMOTE_IMAGE_RE.search(path):
        return None
    return path


class VirtualFieldFile(FieldFile):

    def __init__(self, name, storage=None, upload_to=None):
        super(FieldFile, self).__init__(None, name)
        self.instance = None
        self.field = FileField(
            name='file', upload_to=upload_to,
            storage=storage or get_image_storage())
        self.storage = self.field.storage
        self._committed = True

    def get_directory_name(self):
        return self.field.get_directory_name()

    def get_filename(self, filename):
        return self.field.get_filename(filename)

    def generate_filename(self, filename):
        return self.field.generate_filename(None, filename)

    def save(self, *args, **kwargs):
        raise NotImplementedError

    def delete(self, *args, **kwargs):
        raise NotImplementedError

    @cached_property
    def dimensions(self):
        try:
            close = self.closed
            self.open()
            return get_image_dimensions(self, close=close)
        except:
            return (0, 0)

    @cached_property
    def width(self):
        w, h = self.dimensions
        return w

    @cached_property
    def height(self):
        w, h = self.dimensions
        return h


class ImageFile(VirtualFieldFile):

    _path = None

    preview_image = None
    metadata = None

    def __init__(self, path, upload_to=None, preview_w=None, preview_h=None):
        self.upload_to = upload_to
        self.preview_width = preview_w
        self.preview_height = preview_h
        self.metadata = {}

        if not path:
            self.name = None
            return

        stored_name = normalize_stored_image_name(path)
        if stored_name is None:
            # url on other server? download it.
            self._path = self.download_image_url(path)
        elif stored_name.startswith('//'):
            # urlopen() cannot fetch a protocol-relative URL, and storage
            # rejects it because it resolves outside MEDIA_ROOT.
            self._path = None
        elif get_image_storage().exists(stored_name):
            self._path = stored_name

        if not self._path:
            self.name = None
            return

        super(ImageFile, self).__init__(self._path)

        if self:
            self.preview_image = self.get_for_size('preview')

    def download_image_url(self, url):
        from cropduster.models import StandaloneImage
        from cropduster.services.upload import store_upload

        if not cropduster_settings.CROPDUSTER_REMOTE_IMAGE_FETCH:
            raise SuspiciousOperation(REMOTE_FETCH_REFUSED % url)

        image_contents = urlopen(url).read()
        md5_hash = hashlib.md5()
        md5_hash.update(image_contents)
        try:
            standalone_image = StandaloneImage.objects.get(md5=md5_hash.hexdigest())
        except StandaloneImage.DoesNotExist:
            pass
        else:
            return get_relative_media_url(standalone_image.image.name)

        parse_result = urlparse(url)

        result = store_upload(
            SimpleUploadedFile(
                os.path.basename(parse_result.path), image_contents),
            upload_to=self.upload_to,
            preview_size=(self.preview_width, self.preview_height))
        return result.original_name

    def __nonzero__(self):
        """When evaluated as boolean, base on whether self._path is not None"""
        if not self._path:
            return False
        return super(ImageFile, self).__nonzero__()

    def get_for_size(self, size_slug='original'):
        from cropduster.models import Image

        image = Image.get_file_for_size(self, size_slug)
        if size_slug == 'preview':
            if not get_image_storage().exists(image.name):
                Image.save_preview_file(self, preview_w=self.preview_width, preview_h=self.preview_height)
        return image
