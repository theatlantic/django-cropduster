from __future__ import division

import hashlib
import random
from io import BytesIO
import os
import time
from datetime import datetime

from django.core.exceptions import ImproperlyConfigured, ObjectDoesNotExist
from django.core.files.storage import FileSystemStorage
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import connection, models
from django.utils import six
from django.utils.encoding import python_2_unicode_compatible
from django.utils.six.moves import xrange
from django.core.files.storage import default_storage, FileSystemStorage

import PIL.Image

from generic_plus.utils import get_relative_media_url

from .exceptions import CropDusterResizeException
from .fields import (
    CropDusterField, ReverseForeignRelation, CropDusterImageField,
    CropDusterSimpleImageField)
from .files import VirtualFieldFile
from .resizing import Size, Box, Crop, SizeAlias
from .utils import process_image
from . import settings as cropduster_settings


__all__ = ('Image', 'Thumb', 'StandaloneImage', 'CropDusterField', 'Size', 'Box', 'Crop')


def safe_str_path(file_path):
    """
    Convert unicode paths to bytestrings so that os.path does not throw
    string conversion errors
    """
    if six.PY2 and isinstance(file_path, unicode):
        return file_path.encode('utf-8')
    return file_path


@python_2_unicode_compatible
class Thumb(models.Model):

    name = models.CharField(max_length=255, db_index=True)
    width = models.PositiveIntegerField(default=0, blank=True, null=True)
    height = models.PositiveIntegerField(default=0, blank=True, null=True)

    # For a given thumbnail, it either has crop data or it references
    # another thumbnail with crop data
    reference_thumb = models.ForeignKey('Thumb', blank=True, null=True,
            related_name='auto_set', on_delete=models.CASCADE)

    crop_x = models.PositiveIntegerField(blank=True, null=True)
    crop_y = models.PositiveIntegerField(blank=True, null=True)
    crop_w = models.PositiveIntegerField(blank=True, null=True)
    crop_h = models.PositiveIntegerField(blank=True, null=True)

    date_modified = models.DateTimeField(auto_now=True)

    image = models.ForeignKey('Image', related_name='+', null=True, blank=True,
        on_delete=models.CASCADE)

    class Meta:
        app_label = cropduster_settings.CROPDUSTER_APP_LABEL
        db_table = '%s_thumb' % cropduster_settings.CROPDUSTER_DB_PREFIX

    def __str__(self):
        return self.name

    @property
    def image_file(self):
        return Image.get_file_for_size(
            image=self.image, size_name=self.name,
            tmp=not(getattr(self.image, 'pk', None)))

    @property
    def url(self):
        return self.image_file.url if self.image_file else ''

    @property
    def cache_safe_url(self):
        """A URL that includes a GET parameter that changes upon modification"""
        cache_buster = time.mktime(self.date_modified.timetuple())
        return "%s?mod=%d" % (self.url, cache_buster)

    @property
    def path(self):
        return self.image_file.path if self.image_file else ''

    @property
    def image_name(self):
        return self.image_file.name if self.image_file else ''

    def save(self, *args, **kwargs):
        if self.pk and self.image_id:
            try:
                # save new file without tmp suffix
                tmp_image_path = self.image.get_image_path(self.name, tmp=True)
                image_path = self.image.get_image_path(self.name)
                with default_storage.open(tmp_image_path) as tmp_file:
                    with default_storage.open(image_path, 'wb') as f:
                        f.write(tmp_file.read())
                # delete tmp file
                default_storage.delete(tmp_image_path)
            except (IOError, OSError):
                pass
        return super(Thumb, self).save(*args, **kwargs)

    def to_dict(self):
        """Returns a dict of the thumb's values which are JSON serializable."""
        dct = {}
        for k, v in six.iteritems(vars(self)):
            if isinstance(v, (six.string_types, float, bool, type(None))):
                dct[k] = v
            if isinstance(v, six.integer_types):
                dct[k] = v
        return dct

    def get_crop_box(self):
        if self.reference_thumb:
            ref_thumb = self.reference_thumb
        else:
            ref_thumb = self
        x1, y1 = ref_thumb.crop_x, ref_thumb.crop_y
        x2, y2 = x1 + ref_thumb.crop_w, y1 + ref_thumb.crop_h
        if any([getattr(ref_thumb, 'crop_%s' % a) is None for a in ['x', 'y', 'w', 'h']]):
            return None
        return Box(x1, y1, x2, y2)

    def crop(self, original_image=None, size=None, w=None, h=None):
        if original_image is None:
            if not self.pk:
                raise Exception(
                    u"The `original_image` argument is required for"
                    u" thumbnails which have not yet been saved")

            if not self.image_id:
                raise Exception(
                    u"The `original_image` argument is required for"
                    u" thumbnails which are not associated with an image")

            original_image = self.image

        crop_box = self.get_crop_box()
        if crop_box is None:
            raise Exception("Cannot crop thumbnail without crop data")
        crop = Crop(crop_box, original_image)

        width = size.w or w
        height = size.h or h

        if self.reference_thumb:
            best_fit_kwargs = {
                'min_w': size.min_w or width,
                'min_h': size.min_h or height,
            }
            if width and height:
                best_fit_kwargs.update({'w': width, 'h': height})
            crop = crop.best_fit(**best_fit_kwargs)
        if not width and not height:
            width, height = crop.box.size
        elif not width:
            width = crop.box.w * (height / crop.box.h)
            width = min(int(round(width)), crop.bounds.w)
        elif not height:
            height = crop.box.h * (width / crop.box.w)
            height = min(int(round(height)), crop.bounds.h)

        new_w, new_h = crop.box.size
        if new_w < width or new_h < height:
            raise CropDusterResizeException(
                u"Crop box (%dx%d) is too small for resize to (%dx%d)" % (new_w, new_h, width, height))

        # Scale our initial width and height based on the max_w and max_h
        max_scales = []
        if size.max_w and size.max_w < width:
            max_scales.append(size.max_w / width)
        if size.max_h and size.max_h < height:
            max_scales.append(size.max_h / height)
        if max_scales:
            max_scale = min(max_scales)
            width = int(round(width * max_scale))
            height = int(round(height * max_scale))

        self.width = width
        self.height = height

        return crop


class StrFileSystemStorage(FileSystemStorage):
    """Converts paths to byte-strings.

    Linux uses str/bytes for file paths, but Django tries to use unicode.
    """
    def path(self, name):
        path = super(StrFileSystemStorage, self).path(name)
        if six.PY2 and isinstance(path, unicode):
            path = path.encode('utf-8')
        return path


image_storage = StrFileSystemStorage()


def generate_filename(instance, filename):
    return filename


@python_2_unicode_compatible
class Image(models.Model):

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    content_object = GenericForeignKey('content_type', 'object_id')
    field_identifier = models.SlugField(null=False, blank=True, default="")

    prev_object_id = models.PositiveIntegerField(null=True, blank=True)
    prev_content_object = GenericForeignKey('content_type', 'prev_object_id')

    width = models.PositiveIntegerField(blank=True, null=True)
    height = models.PositiveIntegerField(blank=True, null=True)

    image = CropDusterSimpleImageField(db_index=True,
        upload_to=generate_filename, db_column='path',
        width_field='width', height_field='height')

    thumbs = ReverseForeignRelation(Thumb, field_name='image')

    date_created = models.DateTimeField(auto_now_add=True)
    date_modified = models.DateTimeField(auto_now=True)

    attribution = models.CharField(max_length=255, blank=True, null=True)
    attribution_link = models.URLField(max_length=255, blank=True, null=True)
    caption = models.TextField(blank=True, null=True)
    alt_text = models.TextField("Alt Text", blank=True, default="")

    class Meta:
        app_label = cropduster_settings.CROPDUSTER_APP_LABEL
        db_table = '%s_image' % cropduster_settings.CROPDUSTER_DB_PREFIX
        unique_together = ("content_type", "object_id", "field_identifier")

    def __str__(self):
        return self.get_image_url()

    # TODO: deprecated
    @property
    def path(self):
        return self.name

    @property
    def name(self):
        return self.image.name if self.image else None

    @property
    def url(self):
        return self.image.url if self.image else None

    @property
    def extension(self):
        ''' returns the file extension with a dot (.) prepended to it '''
        if not self.image:
            return u''
        return os.path.splitext(safe_str_path(self.image.path))[1]

    @staticmethod
    def get_file_for_size(image, size_name='original', tmp=False):
        if isinstance(image, six.string_types):
            image = VirtualFieldFile(image)
        if not image:
            return None
        path, basename = os.path.split(safe_str_path(image.name))
        filename, extension = os.path.splitext(basename)
        if size_name == 'preview':
            size_name = '_preview'
        if tmp:
            size_name = '%s_tmp' % size_name
        return VirtualFieldFile(
            '/'.join([
                path,
                safe_str_path(size_name) + extension]))

    @classmethod
    def save_preview_file(cls, image_file, preview_w=None, preview_h=None):
        with image_file as f:
            f.open()
            pil_img = PIL.Image.open(BytesIO(f.read()))
            pil_img.filename = f.name
        orig_w, orig_h = pil_img.size

        preview_w = preview_w or cropduster_settings.CROPDUSTER_PREVIEW_WIDTH
        preview_h = preview_h or cropduster_settings.CROPDUSTER_PREVIEW_HEIGHT

        resize_ratio = min(preview_w / orig_w, preview_h / orig_h)

        def fit_preview(im):
            if resize_ratio < 1:
                w = int(round(orig_w * resize_ratio))
                h = int(round(orig_h * resize_ratio))
                preview_img = im.resize((w, h), PIL.Image.ANTIALIAS)
            else:
                w, h = orig_w, orig_h
                preview_img = im
            return preview_img

        preview_file = cls.get_file_for_size(image_file, '_preview')
        process_image(pil_img, safe_str_path(preview_file.name), fit_preview)
        return preview_file

    def save_preview(self, preview_w=None, preview_h=None):
        return Image.save_preview_file(self.image, preview_w=preview_w, preview_h=preview_h)

    def has_thumb(self, size_name):
        try:
            self.thumbs.get(name=size_name)
        except Thumb.DoesNotExist:
            return False
        else:
            return True

    def get_image_filesize(self, size_name='original'):
        size_name = size_name or 'original'
        if size_name != 'original' and not self.has_thumb(size_name):
            return 0
        return os.path.getsize(self.get_image_path(size_name))

    def get_image_filename(self, size_name='original'):
        size_name = size_name or 'original'
        if size_name != 'original' and not self.has_thumb(size_name):
            return ''
        return os.path.basename(self.get_image_path(size_name))

    def get_image_path(self, size_name='original', tmp=False):
        size_name = size_name or 'original'
        converted = Image.get_file_for_size(self.image, size_name, tmp=tmp)
        if not converted:
            return u''
        else:
            return converted.name

    def save(self, **kwargs):
        self.date_modified = datetime.now()
        if self.field_identifier is None:
            self.field_identifier = ""
        if not self.pk and self.content_type and self.object_id:
            try:
                original = Image.objects.get(content_type=self.content_type,
                                             object_id=self.object_id,
                                             field_identifier=self.field_identifier,
                                             prev_object_id__isnull=True)
            except Image.DoesNotExist:
                pass
            else:
                original.prev_object_id = original.object_id
                original.object_id = None
                original.save()

        super(Image, self).save(**kwargs)

        # If the Image has changed, we need to make sure the related field on the
        # model class has also been updated
        model_class = self.content_type.model_class()

        fields_with_models = [
            (f, f.model if f.model != model_class else None)
            for f in model_class._meta.get_fields()
            if not f.is_relation
            or f.one_to_one
            or (f.many_to_one and f.related_model)]

        for field, field_model_class in fields_with_models:
            field_model_class = field_model_class or model_class
            if (isinstance(field, CropDusterImageField) and
                    field.generic_field.field_identifier == self.field_identifier):
                field_model_class.objects.filter(pk=self.object_id).update(**{field.attname: self.path or ''})

    def get_image_url(self, size_name='original', tmp=False):
        converted = Image.get_file_for_size(self.image, size_name, tmp=tmp)
        return getattr(converted, 'url', None) or u''

    def get_image_size(self, size_name=None):
        """
        Returns tuple of a thumbnail's size (width, height).
        When first parameter unspecified returns a tuple of the size of
        the original image.
        """
        if size_name is not None:
            try:
                thumb = self.thumbs.get(name=size_name)
            except Thumb.DoesNotExist:
                return (0, 0)
            else:
                return (thumb.width, thumb.height)

        # Get the original size
        if not self.image or not default_storage.exists(safe_str_path(self.image.path)):
            return (0, 0)
        elif self.width and self.height:
            return (self.width, self.height)
        else:
            try:
                img = PIL.Image.open(safe_str_path(self.image.path))
            except (IOError, ValueError, TypeError):
                return (0, 0)
            else:
                return img.size

    def delete(self, *args, **kwargs):
        obj = self.content_object
        image_name = self.image.name if (self.image) else None

        super(Image, self).delete(*args, **kwargs)

        if not obj or not image_name:
            return

        def field_matches(f):
            if not isinstance(f, CropDusterImageField):
                return False
            obj_image_name = getattr(getattr(obj, f.name, None), 'name', None)
            return (obj_image_name == image_name)

        try:
            cropduster_field = [f for f in obj._meta.fields if field_matches(f)][0]
        except IndexError:
            pass
        else:
            # Clear the file field on the generic-related instance
            setattr(obj, cropduster_field.name, None)
            obj.save()

    def save_size(self, size, thumb=None, image=None, tmp=False, standalone=False,
                  permissive=False, skip_existing=False):
        thumbs = {}
        if not image and not self.image:
            raise Exception("Cannot save sizes without an image")

        if not image:
            with default_storage.open(self.image.name) as f:
                image = PIL.Image.open(f)
                image.filename = self.image.name

        if standalone:
            if not StandaloneImage:
                raise ImproperlyConfigured(u"standalone mode used, but not installed.")
            return self._save_standalone_thumb(size, image, thumb)

        for sz in Size.flatten([size]):
            if self.pk and skip_existing and default_storage.exists(self.get_image_path(sz.name)):
                try:
                    existing_thumb = self.thumbs.get(name=sz.name)
                except Thumb.DoesNotExist:
                    pass
                else:
                    thumbs[sz.name] = existing_thumb
                    continue
            try:
                if thumb and sz.is_auto:
                    new_thumb = self._save_thumb(sz, image, ref_thumb=thumb, tmp=tmp)
                else:
                    thumb = new_thumb = self._save_thumb(sz, image, thumb, tmp=tmp)
            except CropDusterResizeException:
                if permissive or not sz.required:
                    if not sz.is_auto:
                        thumb = new_thumb = None
                    continue
                else:
                    raise

            if new_thumb:
                thumbs[sz.name] = new_thumb
        return thumbs

    def _save_standalone_thumb(self, size, image=None, thumb=None):
        if not thumb:
            thumb = Thumb(
                width=self.width, height=self.height,
                crop_x=0, crop_y=0, crop_w=self.width, crop_h=self.height)
        thumb.name = ''.join([random.choice('abcdefghijklmnopqrstuvwxyz0123456789') for i in xrange(0, 8)])
        thumb_path = self.get_image_path(thumb.name)
        thumb_crop = thumb.crop(image, size,
            w=(size.w or thumb.crop_w),
            h=(size.h or thumb.crop_h))
        thumb_image = thumb_crop.create_image(thumb_path, width=thumb.width, height=thumb.height)
        thumb_image.crop.add_xmp_to_crop(thumb_path, size, original_image=image)
        md5 = hashlib.md5()
        with default_storage.open(thumb_path, mode='rb') as f:
            image_contents = f.read()
        md5.update(image_contents)
        thumb.name = md5.hexdigest()[0:9]
        new_path = self.get_image_path(thumb.name)
        with default_storage.open(new_path, 'wb') as f:
            f.write(image_contents)
        default_storage.delete(thumb_path)
        return thumb

    def _save_thumb(self, size, image=None, thumb=None, ref_thumb=None, tmp=False, commit=True):
        image = image or PIL.Image.open(safe_str_path(self.image.path))
        if not thumb and self.pk:
            try:
                thumb = self.thumbs.get(name=size.name)
            except Thumb.DoesNotExist:
                pass
        if not thumb:
            thumb = Thumb(name=size.name)
        elif not thumb.name:
            thumb.name = size.name

        if size.is_auto:
            thumb.reference_thumb = ref_thumb or thumb.reference_thumb

        thumb_crop = thumb.crop(image, size)
        thumb_path = self.get_image_path(size.name, tmp=tmp)
        thumb_image = thumb_crop.create_image(thumb_path, width=thumb.width, height=thumb.height)

        if StandaloneImage:
            thumb_image.crop.add_xmp_to_crop(thumb_path, size, original_image=image)

        if commit:
            thumb.save()
        return thumb


try:
    from cropduster.standalone.models import StandaloneImage
except:
    raise
    class FalseMeta(type):
        def __nonzero__(cls): return False
        __bool__ = __nonzero__

    @six.add_metaclass(FalseMeta)
    class StandaloneImage(object):
        DoesNotExist = type('DoesNotExist', (ObjectDoesNotExist,), {})
