import os
import re

from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes import generic
from django.db import models
from django.conf import settings

import PIL.Image
from jsonutil import jsonutil

from .utils import relpath, get_aspect_ratios, validate_sizes
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
        Images are stored relative to the CROPDUSTER_UPLOAD_PATH.
        This method accepts a path relative to MEDIA_ROOT and
        does the relative path conversion for the get() call.
        """
        if relative_path[0] == '/':
            relative_path = relative_path[1:]
        media_path = os.path.join(settings.MEDIA_ROOT, relative_path)
        cropduster_rel_path = relpath(cropduster_settings.CROPDUSTER_UPLOAD_PATH,
            media_path)
        cropduster_rel_path = re.sub(r'/original\.[^/]+$', '',
            cropduster_rel_path)
        return self.get(path=cropduster_rel_path)


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

    default_thumb = models.CharField(max_length=255)

    thumbs = models.ManyToManyField(
        'cropduster.Thumb',
        related_name = 'thumbs',
        verbose_name = 'thumbs',
        null = True,
        blank = True
    )

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
        
    def default_thumb_url(self, use_temp=False):
        return self.get_image_url(self.default_thumb, use_temp)

    def get_image_path(self, size_name=None, use_temp=False):
        if size_name is None:
            size_name = 'original'
        
        if use_temp:
            size_name += '_tmp'

        return os.path.join(cropduster_settings.CROPDUSTER_UPLOAD_PATH, self.path, size_name + self.extension)

    def get_relative_image_path(self, size_name=None, use_temp=False):
        img_path = self.get_image_path(size_name, use_temp)
        return relpath(settings.MEDIA_ROOT, img_path)

    def has_thumb(self, size_name):
        try:
            self.thumbs.get(name=size_name)
        except Thumb.DoesNotExist:
            return False
        else:
            return True
    
    def save(self, **kwargs):

        has_changed = False
        try:
            img = self.objects.get(pk=self.id)

            if self.crop_x != img.crop_x:
                has_changed = True
            elif self.crop_y != img.crop_y:
                has_changed = True
            elif self.crop_w != img.crop_w:
                has_changed = True
            elif self.crop_h != img.crop_h:
                has_changed = True
            elif self.path != img.path:
                has_changed = True
            elif self.ext != img.ext:
                has_changed = True
        except:
            has_changed = True

        if has_changed:
            try:
                for thumb in self.thumbs.all():
                    try:
                        os.rename(
                            self.get_image_path(thumb.name, use_temp=True),
                            self.get_image_path(thumb.name)
                        )
                    except:
                        pass
            except:
                pass

        return super(Image, self).save(**kwargs)
        
    
    def get_image_url(self, size_name=None, use_temp=False):
        
        if self.path is None:
            return ''
        
        if size_name is None:
            size_name = 'original'
        
        if use_temp:
            size_name += '_tmp'
        
        relative_path = relpath(settings.MEDIA_ROOT, cropduster_settings.CROPDUSTER_UPLOAD_PATH)
        if re.match(r'\.\.', relative_path):
            raise Exception("Upload path is outside of static root")
        url_root = settings.MEDIA_URL + '/' + relative_path + '/'
        url = url_root + self.path + '/' + size_name + self.extension
        url = re.sub(r'(?<!:)/+', '/', url)
        return url
    
    def get_base_dir_name(self):
        ''' 
        returns the directory that contain the various sizes of images, based off of the 
        original file name
        '''
        
        path, dir_name = os.path.split(self.path)
        return dir_name
    
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
                return img.size
            except:
                pass
        try:
            thumb = self.thumbs.get(name=size_name)
            return (thumb.width, thumb.height)
        except:
            return (0, 0)

    def get_image_filesize(self, size_name=None):
        """Returns the filesize of the thumbnail.  Defaults to the original image."""
        if size_name is None:
            return os.path.getsize(self.get_image_path())
        else:
            if self.has_thumb(size_name):
                return os.path.getsize(self.get_image_path(size_name))
            else:
                return 0
            
    def get_image_filename(self, size_name=None):
        """Returns the filename of the thumbnail.  Defaults to the original image."""
        if size_name is None:
            return os.path.basename(self.get_image_path())
        else:
            if self.has_thumb(size_name):
                return os.path.basename(self.get_image_path(size_name))
            else:
                return ''
    
    def save_thumb(self, name, width, height):
        """
        Check if a thumbnail already exists for the current image,
        otherwise 
        """
        thumb = None
        try:
            thumb = self.thumbs.get(name=name)
            thumb.width = width
            thumb.height = height
            thumb.name = name
            thumb.save()
        except:
            thumb = Thumb(
                width = width,
                height = height,
                name = name
            )
            thumb.save()
        return thumb


from .related import GenericRelation

class CropDusterField(GenericRelation):

    sizes = None
    auto_sizes = None
    default_thumb = None

    def __init__(self, verbose_name=None, **kwargs):
        sizes = kwargs.pop('sizes', None)
        auto_sizes = kwargs.pop('auto_sizes', None)
        default_thumb = kwargs.pop('default_thumb', None)

        if default_thumb is None:
            raise ValueError("default_thumb attribute must be defined.")

        default_thumb_key_exists = False

        try:
            self._sizes_validate(sizes)
            if default_thumb in sizes.keys():
                default_thumb_key_exists = True
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
            if default_thumb in auto_sizes.keys():
                default_thumb_key_exists = True

        if not default_thumb_key_exists:
            raise ValueError("default_thumb attribute does not exist in either sizes or auto_sizes dict.")

        self.sizes = sizes
        self.auto_sizes = auto_sizes
        self.default_thumb = default_thumb

        kwargs['to'] = Image
        super(CropDusterField, self).__init__(verbose_name=verbose_name, **kwargs)

    def _sizes_validate(self, sizes, is_auto=False):
        validate_sizes(sizes)    
        if not is_auto:
            aspect_ratios = get_aspect_ratios(sizes)
            if len(aspect_ratios) > 1:
                raise ValueError("More than one aspect ratio: %s" % jsonutil.dumps(aspect_ratios))

    def formfield(self, **kwargs):
        from .forms import cropduster_formfield_factory, cropduster_widget_factory
        formfield_cls = cropduster_formfield_factory(*(
            self.sizes,
            self.auto_sizes,
            self.default_thumb,))
        widget_cls = cropduster_widget_factory(*(
            self.sizes,
            self.auto_sizes,
            self.default_thumb,))

        defaults = {'widget': widget_cls}
        defaults = {'form_class': formfield_cls}
        defaults.update(kwargs)
        return super(CropDusterField, self).formfield(**defaults)


from .patch import patch_model_admin
patch_model_admin()


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
                "default_thumb": ["default_thumb", {}],
            },
        ),
    ], patterns=["^cropduster\.models\.CropDusterField"])
