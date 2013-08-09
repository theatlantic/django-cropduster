import os
import re

from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes import generic
from django.db import models
from django.conf import settings

import PIL.Image
from jsonutil import jsonutil

from .related import CropDusterGenericRelation
from .utils import get_aspect_ratios, validate_sizes
from . import settings as cropduster_settings


class Thumb(models.Model):
    name = models.CharField(max_length=255, db_index=True)
    height = models.PositiveIntegerField(default=0, blank=True, null=True)
    width = models.PositiveIntegerField(default=0, blank=True, null=True)

    def __unicode__(self):
        return self.name

    class Meta:
        app_label = cropduster_settings.CROPDUSTER_APP_LABEL
        db_table = '%s_thumb' % cropduster_settings.CROPDUSTER_DB_PREFIX


class ImageManager(models.Manager):

    def get_by_relpath(self, relative_path):
        """
        This method accepts a path relative to MEDIA_ROOT and
        does the relative path conversion for the get() call.
        """
        if relative_path[0] == '/':
            relative_path = relative_path[1:]
        relative_path = re.sub(r'/original\.[^/]+$', '', relative_path)
        return self.get(path=relative_path)


class Image(models.Model):

    objects = ImageManager()

    content_type = models.ForeignKey(ContentType)
    object_id = models.PositiveIntegerField()
    content_object = generic.GenericForeignKey('content_type', 'object_id')

    crop_x = models.PositiveIntegerField(default=0, blank=True, null=True)
    crop_y = models.PositiveIntegerField(default=0, blank=True, null=True)
    crop_w = models.PositiveIntegerField(default=0, blank=True, null=True)
    crop_h = models.PositiveIntegerField(default=0, blank=True, null=True)

    path = models.CharField(max_length=255, db_index=True)
    _extension = models.CharField(max_length=4, db_column='extension')

    thumbs = models.ManyToManyField('cropduster.Thumb',
        related_name='thumbs',
        verbose_name='thumbs',
        null=True,
        blank=True)

    attribution = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        app_label = cropduster_settings.CROPDUSTER_APP_LABEL
        db_table = '%s_image' % cropduster_settings.CROPDUSTER_DB_PREFIX
        unique_together = ("content_type", "object_id")

    def __unicode__(self):
        return self.get_image_url()

    @property
    def extension(self):
        ''' returns the file extension with a dot (.) prepended to it '''
        return '.' + self._extension

    @extension.setter
    def extension(self, val):
        """ ensures that file extension is lower case and doesn't have a double dot (.) """
        self._extension = val.lower().replace('.', '')

    def get_image_path(self, size_name='original', use_temp=False):
        if use_temp:
            size_name += '_tmp'
        return os.path.join(settings.MEDIA_ROOT, self.path, size_name + self.extension)

    def get_relative_image_path(self, size_name='original', use_temp=False):
        if use_temp:
            size_name += '_tmp'
        return u'/'.join([self.path, size_name + self.extension])

    def has_thumb(self, size_name):
        try:
            self.thumbs.get(name=size_name)
        except Thumb.DoesNotExist:
            return False
        else:
            return True

    def save(self, **kwargs):
        if not self.pk:
            has_changed = False
        else:
            orig = Image.objects.get(pk=self.pk)
            attnames = [f.attname for f in self._meta.fields]
            has_changed = any([getattr(orig, n) != getattr(self, n) for n in attnames])

        if has_changed:
            for thumb in self.thumbs.all():
                try:
                    os.rename(
                        self.get_image_path(thumb.name, use_temp=True),
                        self.get_image_path(thumb.name))
                except:
                    pass

        return super(Image, self).save(**kwargs)


    def get_image_url(self, size_name='original', use_temp=False):
        if self.path is None:
            return ''
        if use_temp:
            size_name += '_tmp'
        url = u'/'.join([settings.MEDIA_URL, self.path, size_name + self.extension])
        return re.sub(r'(?<!:)/+', '/', url)

    def get_image_size(self, size_name=None):
        """
        Returns tuple of a thumbnail's size (width, height).
        When first parameter unspecified returns a tuple of the size of
        the original image.
        """
        if size_name is None:
            # Get the original size
            try:
                img = PIL.Image.open(self.get_image_path())
            except:
                return (0, 0)
            else:
                return img.size
        try:
            thumb = self.thumbs.get(name=size_name)
        except Thumb.DoesNotExist:
            return (0, 0)
        else:
            return (thumb.width, thumb.height)

    def save_thumb(self, name, width, height):
        """
        Check if a thumbnail already exists for the current image,
        otherwise
        """
        thumb = Thumb()
        if self.pk:
            try:
                thumb = self.thumbs.get(name=name)
            except Thumb.DoesNotExist:
                pass
        thumb.width = width
        thumb.height = height
        thumb.name = name
        thumb.save()
        return thumb


class CropDusterField(CropDusterGenericRelation):

    sizes = None
    auto_sizes = None

    def __init__(self, verbose_name=None, **kwargs):
        sizes = kwargs.pop('sizes', None)
        auto_sizes = kwargs.pop('auto_sizes', None)

        try:
            self._sizes_validate(sizes)
        except ValueError as e:
            # Maybe the sizes is none and the auto_sizes is valid, let's
            # try that
            try:
                self._sizes_validate(auto_sizes, is_auto=True)
            except:
                # raise the original exception
                raise e

        if auto_sizes is not None:
            self._sizes_validate(auto_sizes, is_auto=True)

        self.sizes = sizes
        self.auto_sizes = auto_sizes

        kwargs['to'] = Image
        super(CropDusterField, self).__init__(verbose_name=verbose_name, **kwargs)

    def _sizes_validate(self, sizes, is_auto=False):
        validate_sizes(sizes)
        if not is_auto:
            aspect_ratios = get_aspect_ratios(sizes)
            if len(aspect_ratios) > 1:
                raise ValueError("More than one aspect ratio: %s" % jsonutil.dumps(aspect_ratios))

    def formfield(self, **kwargs):
        from .forms import cropduster_formfield_factory
        from .widgets import cropduster_widget_factory

        factory_kwargs = {
            'sizes': self.sizes,
            'auto_sizes': self.auto_sizes,
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
                "sizes": ["sizes", {}],
                "auto_sizes": ["auto_sizes", {"default": None}],
            },
        ),
    ], patterns=["^cropduster\.models\.CropDusterField"])
