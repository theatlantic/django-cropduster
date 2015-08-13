from __future__ import division

import six

from six.moves import xrange

import hashlib
import random
import os
from datetime import datetime

from django.core.exceptions import ImproperlyConfigured, ObjectDoesNotExist
from django.core.files.storage import FileSystemStorage
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db import transaction

try:
    from django.contrib.contenttypes.fields import GenericForeignKey
except ImportError:
    from django.contrib.contenttypes.generic import GenericForeignKey

import PIL.Image

from generic_plus.utils import get_relative_media_url

from .exceptions import CropDusterResizeException
from .fields import (
    CropDusterField, ReverseForeignRelation, CropDusterImageField,
    CropDusterSimpleImageField)
from .files import VirtualFieldFile
from .resizing import Size, Box, Crop
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


class Thumb(models.Model):

    name = models.CharField(max_length=255, db_index=True)
    width = models.PositiveIntegerField(default=0, blank=True, null=True)
    height = models.PositiveIntegerField(default=0, blank=True, null=True)

    # For a given thumbnail, it either has crop data or it references
    # another thumbnail with crop data
    reference_thumb = models.ForeignKey('Thumb', blank=True, null=True,
            related_name='auto_set')

    crop_x = models.PositiveIntegerField(blank=True, null=True)
    crop_y = models.PositiveIntegerField(blank=True, null=True)
    crop_w = models.PositiveIntegerField(blank=True, null=True)
    crop_h = models.PositiveIntegerField(blank=True, null=True)

    date_modified = models.DateTimeField(auto_now=True)

    image = models.ForeignKey('Image', related_name='+', null=True, blank=True)

    class Meta:
        app_label = cropduster_settings.CROPDUSTER_APP_LABEL
        db_table = '%s_thumb' % cropduster_settings.CROPDUSTER_DB_PREFIX

    def __unicode__(self):
        return self.name

    @property
    def image_file(self):
        return Image.get_file_for_size(image=self.image, size_name=self.name)

    @property
    def url(self):
        return self.image_file.url if self.image_file else ''

    @property
    def path(self):
        return self.image_file.path if self.image_file else ''

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if self.pk:
                try:
                    orig_thumb = Thumb.objects.select_for_update().get(pk=self.pk)
                except Thumb.DoesNotExist:
                    pass
                else:
                    if self.image_id and not orig_thumb.image_id:
                        try:
                            os.rename(
                                self.image.get_image_path(self.name, tmp=True),
                                self.image.get_image_path(self.name))
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

    def crop(self, output_filename, original_image=None, w=None, h=None, min_w=None, min_h=None, max_w=None, max_h=None):
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

        self.width = w or None
        self.height = h or None

        if self.reference_thumb:
            best_fit_kwargs = {
                'min_w': min_w or self.width,
                'min_h': min_h or self.height,
            }
            if self.width and self.height:
                best_fit_kwargs.update({'w': self.width, 'h': self.height})
            fit = crop.best_fit(**best_fit_kwargs)
            if not self.width and not self.height:
                self.width, self.height = fit.box.size
            elif not self.width:
                width = fit.box.w * (self.height / fit.box.h)
                self.width = min(int(round(width)), crop.bounds.w)
            elif not self.height:
                height = fit.box.h * (self.width / fit.box.w)
                self.height = min(int(round(height)), crop.bounds.h)
            new_image = fit.create_image(output_filename, width=self.width, height=self.height, max_w=max_w, max_h=max_h)
        else:
            if w and h:
                self.width = w
                self.height = h
            elif w:
                height = crop_box.h * (w / crop_box.w)
                self.height = min(int(round(height)), crop.bounds.h)
            elif h:
                width = crop_box.w * (h / crop_box.h)
                self.width = min(int(round(width)), crop.bounds.w)
            else:
                self.width, self.height = crop.box.size

            new_image = crop.create_image(output_filename, width=self.width, height=self.height, max_w=max_w, max_h=max_h)

        self.width, self.height = new_image.size
        return new_image


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


class Image(models.Model):

    content_type = models.ForeignKey(ContentType)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    content_object = GenericForeignKey('content_type', 'object_id')
    field_identifier = models.SlugField(null=False, blank=True, default="")

    prev_object_id = models.PositiveIntegerField(null=True, blank=True)
    prev_content_object = GenericForeignKey('content_type', 'prev_object_id')

    width = models.PositiveIntegerField(blank=True, null=True)
    height = models.PositiveIntegerField(blank=True, null=True)

    image = CropDusterSimpleImageField(db_index=True,
        upload_to=generate_filename, db_column='path',
        storage=image_storage, width_field='width', height_field='height')

    thumbs = ReverseForeignRelation(Thumb, field_name='image')

    date_created = models.DateTimeField(auto_now_add=True)
    date_modified = models.DateTimeField(auto_now=True)

    attribution = models.CharField(max_length=255, blank=True, null=True)
    attribution_link = models.URLField(max_length=255, blank=True, null=True)
    caption = models.TextField(blank=True, null=True)

    class Meta:
        app_label = cropduster_settings.CROPDUSTER_APP_LABEL
        db_table = '%s_image' % cropduster_settings.CROPDUSTER_DB_PREFIX
        unique_together = ("content_type", "object_id", "field_identifier")

    def __unicode__(self):
        return self.get_image_url()

    @property
    def path(self):
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
        path, basename = os.path.split(safe_str_path(image.path))
        filename, extension = os.path.splitext(basename)
        if size_name == 'preview':
            size_name = '_preview'
        if tmp:
            size_name = '%s_tmp' % size_name
        return VirtualFieldFile(
            '/'.join([
                get_relative_media_url(path),
                safe_str_path(size_name) + extension]))

    @classmethod
    def save_preview_file(cls, image_file, preview_w=None, preview_h=None):
        pil_img = PIL.Image.open(safe_str_path(image_file.path))
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
        process_image(pil_img, safe_str_path(preview_file.path), fit_preview)
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
            return converted.path

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
        for field, field_model_class in model_class._meta.get_fields_with_model():
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
        if not self.image or not os.path.exists(safe_str_path(self.image.path)):
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

    def save_size(self, size, thumb=None, image=None, tmp=False, standalone=False, permissive=False):
        thumbs = {}
        if not image and not self.image:
            raise Exception("Cannot save sizes without an image")

        image = image or PIL.Image.open(safe_str_path(self.image.path))

        if standalone:
            if not StandaloneImage:
                raise ImproperlyConfigured(u"standalone mode used, but not installed.")
            return self._save_thumb(size, image, thumb, standalone=True)

        for sz in Size.flatten([size]):
            try:
                if sz.is_auto:
                    new_thumb = self._save_thumb(sz, image, ref_thumb=thumb, tmp=tmp)
                else:
                    thumb = new_thumb = self._save_thumb(sz, image, thumb, tmp=tmp)
            except CropDusterResizeException:
                if permissive or not sz.required:
                    continue
                else:
                    raise

            if new_thumb:
                thumbs[sz.name] = new_thumb
        return thumbs

    def _save_thumb(self, size, image=None, thumb=None, ref_thumb=None, tmp=False, standalone=False):
        img_save_params = {}
        if image.format == 'JPEG':
            img_save_params['quality'] = cropduster_settings.get_jpeg_quality(self.width, self.height)
        if image.format in ('JPEG', 'PNG') and cropduster_settings.JPEG_SAVE_ICC_SUPPORTED:
            img_save_params['icc_profile'] = image.info.get('icc_profile')

        if not thumb:
            if standalone:
                thumb = Thumb(
                    width=self.width, height=self.height,
                    crop_x=0, crop_y=0, crop_w=self.width, crop_h=self.height)
            elif self.pk:
                try:
                    thumb = self.thumbs.get(name=size.name)
                except Thumb.DoesNotExist:
                    pass

        if standalone:
            thumb.name = ''.join([random.choice('abcdefghijklmnopqrstuvwxyz0123456789') for i in xrange(0, 8)])
        elif not thumb:
            thumb = Thumb(name=size.name)
        elif not thumb.name:
            thumb.name = size.name

        crop_box = None

        if size.is_auto:
            ref_thumb = ref_thumb or thumb.reference_thumb
            if ref_thumb:
                crop_box = ref_thumb.get_crop_box()
        elif thumb:
            crop_box = thumb.get_crop_box()

        if not crop_box:
            return None

        thumb.reference_thumb = ref_thumb

        crop_kwargs = dict([(k, getattr(size, k))
                            for k in ['w', 'h', 'min_w', 'min_h', 'max_w', 'max_h']])
        if standalone and not(size.w or size.h) and (thumb.crop_w and thumb.crop_h):
            crop_kwargs['w'] = thumb.crop_w
            crop_kwargs['h'] = thumb.crop_h

        if standalone:
            thumb_path = self.get_image_path(thumb.name)
        else:
            thumb_path = self.get_image_path(size.name, tmp=tmp)

        thumb_image = thumb.crop(thumb_path, image, **crop_kwargs)

        if StandaloneImage:
            thumb_image.crop.add_xmp_to_crop(thumb_path, size)

        if standalone:
            md5 = hashlib.md5()
            with open(thumb_path, mode='rb') as f:
                md5.update(f.read())
            thumb.name = md5.hexdigest()[0:9]
            os.rename(thumb_path, self.get_image_path(thumb.name))
        else:
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


try:
    from south.modelsinspector import add_introspection_rules, add_ignored_fields
except ImportError:
    pass
else:
    add_ignored_fields(["^cropduster\.fields\.ReverseForeignRelation"])

    def converter(value):
        """Custom south converter so that Size objects serialize properly"""
        if isinstance(value, Size):
            return value.__serialize__()
        try:
            is_sizes_list = all([isinstance(sz, Size) for sz in value])
        except TypeError:
            pass
        else:
            if is_sizes_list:
                return [sz.__serialize__() for sz in value]
        return repr(value)

    add_introspection_rules(rules=[
        (
            (CropDusterField,),
            [],
            {
                "to": ["rel.to", {}],
                "symmetrical": ["rel.symmetrical", {"default": True}],
                "object_id_field": ["object_id_field_name", {"default": "object_id"}],
                "content_type_field": ["content_type_field_name", {"default": "content_type"}],
                "blank": ["blank", {"default": True}],
                "sizes": ["sizes", {"converter": converter}],
            },
        ),
    ], patterns=["^cropduster\.fields\.CropDusterField"])

    add_introspection_rules([], ["^cropduster\.fields\.CropDusterSimpleImageField"])
