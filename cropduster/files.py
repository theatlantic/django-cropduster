from __future__ import division

import os
import re
import hashlib

import PIL.Image

from django.core.files.uploadedfile import SimpleUploadedFile
from django.conf import settings
from django.db.models.fields.files import FieldFile, FileField
from django.utils.functional import cached_property
from django.utils.http import urlunquote_plus
from django.utils.six.moves.urllib import parse as urlparse
from django.utils.six.moves.urllib.request import urlopen

from generic_plus.utils import get_relative_media_url, get_media_path


class VirtualFieldFile(FieldFile):

    def __init__(self, name, storage=None, upload_to=None):
        super(FieldFile, self).__init__(None, name)
        self.instance = None
        self.field = FileField(name='file', upload_to=upload_to, storage=storage)
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
            pil_image = PIL.Image.open(self.path)
        except:
            return (0, 0)
        else:
            return pil_image.size

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

        if '%' in path:
            path = urlunquote_plus(path)

        if path.startswith(settings.MEDIA_URL):
            # Strips leading MEDIA_URL, if starts with
            self._path = get_relative_media_url(path, clean_slashes=False)
        elif re.search(r'^(?:http(?:s)?:)?//', path):
            # url on other server? download it.
            self._path = self.download_image_url(path)
        else:
            abs_path = get_media_path(path)
            if os.path.exists(abs_path):
                self._path = get_relative_media_url(abs_path)

        if not self._path or not os.path.exists(os.path.join(settings.MEDIA_ROOT, self._path)):
            self.name = None
            return

        super(ImageFile, self).__init__(self._path)

        if self:
            self.preview_image = self.get_for_size('preview')

    def download_image_url(self, url):
        from cropduster.models import StandaloneImage
        from cropduster.views.forms import clean_upload_data

        image_contents = urlopen(url).read()
        md5_hash = hashlib.md5()
        md5_hash.update(image_contents)
        try:
            standalone_image = StandaloneImage.objects.get(md5=md5_hash.hexdigest())
        except StandaloneImage.DoesNotExist:
            pass
        else:
            return get_relative_media_url(standalone_image.image.name)

        parse_result = urlparse.urlparse(url)

        fake_upload = SimpleUploadedFile(os.path.basename(parse_result.path), image_contents)
        file_data = clean_upload_data({
            'image': fake_upload,
            'upload_to': self.upload_to,
        })
        return get_relative_media_url(file_data['image'].name)

    def __nonzero__(self):
        """When evaluated as boolean, base on whether self._path is not None"""
        if not self._path:
            return False
        return super(ImageFile, self).__nonzero__()

    def get_for_size(self, size_slug='original'):
        from cropduster.models import Image

        image = Image.get_file_for_size(self, size_slug)
        if size_slug == 'preview':
            if not os.path.exists(image.path):
                Image.save_preview_file(self, preview_w=self.preview_width, preview_h=self.preview_height)
        return image
