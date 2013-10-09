from __future__ import division
import os
import re
from datetime import datetime

from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes import generic
from django.core.files.uploadedfile import UploadedFile
from django.db import models
from django.db.models.fields.files import FieldFile
from django.conf import settings

import PIL.Image

from .related import CropDusterGenericRelation
from .resizing import Size, Box, Crop
from .thumbs import CropDusterThumbField
from . import settings as cropduster_settings


__all__ = ('Image', 'Thumb', 'CropDusterField', 'Size', 'Box', 'Crop')


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

    class Meta:
        app_label = cropduster_settings.CROPDUSTER_APP_LABEL
        db_table = '%s_thumb' % cropduster_settings.CROPDUSTER_DB_PREFIX

    def __unicode__(self):
        return self.name

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

    def crop(self, original_image=None, w=None, h=None, min_w=None, min_h=None):
        if original_image is None:
            if not self.pk:
                raise Exception(
                    u"The `original_image` argument is required for"
                    u" thumbnails which have not yet been saved")

            images = self.image_set.all()
            try:
                original_image = images[0]
            except IndexError:
                raise Exception(
                    u"The `original_image` argument is required for"
                    u" thumbnails which are not associated with an image")
            else:
                # Throw exception if there is more than one image associated
                # with the thumb
                try:
                    images[1]
                except IndexError:
                    pass
                else:
                    raise Exception(
                        u"Thumb has more than one image associated with it")

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
            return fit.create_image(width=self.width, height=self.height)
        else:
            if w and h:
                self.width = w
                self.height = h
            elif w:
                height = crop_box.h * (w / crop_box.w)
                self.height = min(int(round(height)), crop.bounds.h)
            elif h:
                width = crop_box.h * (h / crop_box.h)
                self.width = min(int(round(width)), crop.bounds.w)
            return crop.create_image(width=self.width, height=self.height)


class Image(models.Model):

    content_type = models.ForeignKey(ContentType)
    object_id = models.PositiveIntegerField()
    content_object = generic.GenericForeignKey('content_type', 'object_id')

    @staticmethod
    def generate_filename(instance, filename):
        return filename

    width = models.PositiveIntegerField(blank=True, null=True)
    height = models.PositiveIntegerField(blank=True, null=True)

    image = models.ImageField(db_index=True, upload_to=generate_filename, db_column='path',
        width_field='width', height_field='height')

    thumbs = CropDusterThumbField(Thumb,
        related_name='image_set',
        verbose_name='thumbs',
        null=True,
        blank=True)

    date_created = models.DateTimeField(auto_now_add=True)
    date_modified = models.DateTimeField(auto_now=True)

    attribution = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        app_label = cropduster_settings.CROPDUSTER_APP_LABEL
        db_table = '%s_image' % cropduster_settings.CROPDUSTER_DB_PREFIX
        unique_together = ("content_type", "object_id")

    def __unicode__(self):
        return self.get_image_url()

    @property
    def path(self):
        return self.image.name if self.image else None

    @property
    def extension(self):
        ''' returns the file extension with a dot (.) prepended to it '''
        if not self.image:
            return u''
        return os.path.splitext(self.image.path)[1]

    def get_image_path(self, size_name='original', use_temp=False):
        if not self.image:
            return u''
        if use_temp:
            size_name += '_tmp'
        path, basename = os.path.split(self.image.path)
        filename, extension = os.path.splitext(basename)
        return os.path.join(settings.MEDIA_ROOT, path, size_name + extension)

    def save(self, **kwargs):
        self.date_modified = datetime.now()
        if self.pk:
            original = Image.objects.get(pk=self.pk)
            old_date_modified = original.date_modified or datetime.min
            for thumb in self.thumbs.all():
                if thumb.date_modified > old_date_modified:
                    try:
                        os.rename(
                            self.get_image_path(thumb.name, use_temp=True),
                            self.get_image_path(thumb.name))
                    except (IOError, OSError):
                        pass
        return super(Image, self).save(**kwargs)

    def get_image_url(self, size_name='original', use_temp=False):
        if not self.image:
            return u''

        if use_temp:
            size_name += '_tmp'

        rel_path, basename = os.path.split(self.image.name)
        filename, extension = os.path.splitext(basename)
        url = u'/'.join([settings.MEDIA_URL, rel_path, size_name + extension])
        return re.sub(r'(?<!:)/+', '/', url)

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
        if not self.image or not os.path.exists(self.image.path):
            return (0, 0)
        elif self.width and self.height:
            return (self.width, self.height)
        else:
            try:
                img = PIL.Image.open(self.image.path)
            except (IOError, ValueError, TypeError):
                return (0, 0)
            else:
                return img.size

    def save_size(self, size, thumb=None, image=None, tmp=False):
        thumbs = {}
        if not image and not self.image:
            raise Exception("Cannot save sizes without an image")
        image = image or PIL.Image.open(self.image.path)

        for sz in Size.flatten([size]):
            if sz.is_auto:
                new_thumb = self.save_thumb(sz, image, ref_thumb=thumb, tmp=tmp)
            else:
                thumb = new_thumb = self.save_thumb(sz, image, thumb, tmp=tmp)
            if new_thumb:
                thumbs[sz.name] = new_thumb
        return thumbs

    def save_thumb(self, size, image=None, thumb=None, ref_thumb=None, tmp=False):
        img_save_params = {}
        if image.format == 'JPEG':
            img_save_params['quality'] = 95
        if not thumb:
            thumb = Thumb()
            if self.pk:
                try:
                    thumb = self.thumbs.get(name=size.name)
                except Thumb.DoesNotExist:
                    pass

        thumb.name = size.name

        if size.is_auto:
            ref_thumb = ref_thumb or thumb.reference_thumb
            if ref_thumb:
                crop_box = ref_thumb.get_crop_box()
        elif thumb:
            crop_box = thumb.get_crop_box()

        if not crop_box:
            return None

        thumb.reference_thumb = ref_thumb
        thumb_image = thumb.crop(image, w=size.width, h=size.height, min_w=size.min_w, min_h=size.min_h)
        thumb_path = self.get_image_path(size.name, use_temp=tmp)
        thumb_image.save(thumb_path, **img_save_params)
        thumb.save()
        return thumb


def thumbs_added(sender, **kwargs):
    if kwargs.get('action') != 'pre_add':
        return
    instance = kwargs.get('instance')
    pk_set = kwargs.get('pk_set')

    if isinstance(instance, Thumb):
        thumbs = [instance]
        image_id = list(pk_set)[0]
        image = Image.objects.get(pk=image_id)
    else:
        thumbs = Thumb.objects.filter(pk__in=pk_set)
        image = instance

    for thumb in thumbs:
        try:
            os.rename(
                image.get_image_path(thumb.name, use_temp=True),
                image.get_image_path(thumb.name))
        except (IOError, OSError):
            pass
        for auto_thumb in thumb.auto_set.all():
            try:
                os.rename(
                    image.get_image_path(auto_thumb.name, use_temp=True),
                    image.get_image_path(auto_thumb.name))
            except (IOError, OSError):
                pass


models.signals.m2m_changed.connect(thumbs_added, sender=Image.thumbs.through)


class CropDusterField(CropDusterGenericRelation):

    sizes = None

    def __init__(self, verbose_name=None, **kwargs):
        self.sizes = kwargs.pop('sizes', None)
        kwargs['to'] = kwargs.pop('to', Image)
        super(CropDusterField, self).__init__(verbose_name=verbose_name, **kwargs)

    def save_form_data(self, instance, data):
        super(CropDusterField, self).save_form_data(instance, data)

        # pre_save returns getattr(instance, self.name), which is itself
        # the return value of the descriptor's __get__() method.
        # This method (CropDusterDescriptor.__get__()) has side effects,
        # for the same reason that the descriptors of ImageField and
        # GenericForeignKey have side-effects.
        #
        # So, although we don't _appear_ to be doing anything with the
        # value if not(isinstance(data, UploadedFile)), it is still
        # necessary to call pre_save() for the ImageField part of the
        # instance's CropDusterField to sync.
        value = self.pre_save(instance, False)

        # If we have a file uploaded via the fallback ImageField, make
        # sure that it's saved.
        if isinstance(data, UploadedFile):
            if value and isinstance(value, FieldFile) and not value._committed:
                # save=True saves the instance. Since this field (CropDusterField)
                # is considered a "related field" by Django, its save_form_data()
                # gets called after the instance has already been saved. We need
                # to resave it if we have a new image.
                value.save(value.name, value, save=True)
        else:
            instance.save()

    def formfield(self, **kwargs):
        from .forms import cropduster_formfield_factory
        from .widgets import cropduster_widget_factory

        factory_kwargs = {
            'sizes': self.sizes,
            'related': self.related,
        }
        widget = cropduster_widget_factory(**factory_kwargs)
        formfield = cropduster_formfield_factory(widget=widget, **factory_kwargs)
        widget.parent_admin = formfield.parent_admin = kwargs.pop('parent_admin', None)
        widget.request = formfield.request = kwargs.pop('request', None)
        kwargs.update({
            'widget': widget,
            'form_class': formfield,
        })
        return super(CropDusterField, self).formfield(**kwargs)


from .patch import patch_django
patch_django()


try:
    from south.modelsinspector import add_introspection_rules
except ImportError:
    pass
else:
    def converter(value):
        """Custom south converter so that Size objects serialize properly"""
        if isinstance(value, Size):
            return value.__serialize__()
        try:
            is_sizes_list = all([isinstance(sz, Size) for sz in value])
        except TypeError:
            pass
        else:
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
    ], patterns=["^cropduster\.models\.CropDusterField"])

    add_introspection_rules(
        rules=[((models.ManyToManyField,), [], {})],
        patterns=["^cropduster\.thumbs\.CropDusterThumbField"])
