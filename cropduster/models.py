from __future__ import division

import hashlib
import random
from io import BytesIO
import os
from datetime import datetime

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

import PIL.Image

from .exceptions import CropDusterResizeException
from .fields import (
    CropDusterField, ReverseForeignRelation, CropDusterImageField,
    CropDusterSimpleImageField)
from .files import VirtualFieldFile
from .resizing import Size, Box, Crop, SizeAlias
from .standalone import require_standalone
from .utils import process_image
from .utils.fields import get_cropduster_field, get_image_column_field
from . import settings as cropduster_settings


__all__ = (
    'Image', 'Thumb', 'StandaloneImage', 'CropDusterField', 'Size', 'Box',
    'Crop', 'prime_reference_thumbs')


def prime_reference_thumbs(thumbs):
    """Resolve each reference from the sibling thumbs already in memory."""
    thumbs = [obj for obj in thumbs if isinstance(obj, Thumb)]
    if not thumbs:
        return
    field = Thumb._meta.get_field('reference_thumb')
    if field.attname in thumbs[0].get_deferred_fields():
        return
    by_pk = {thumb.pk: thumb for thumb in thumbs if thumb.pk is not None}
    for thumb in thumbs:
        reference = by_pk.get(thumb.reference_thumb_id)
        if reference is not None:
            field.set_cached_value(thumb, reference)


class ThumbQuerySet(models.QuerySet):

    _prime_reference_thumbs = False

    def with_reference_thumbs(self):
        clone = self._chain()
        clone._prime_reference_thumbs = True
        return clone

    def _clone(self):
        clone = super()._clone()
        clone._prime_reference_thumbs = self._prime_reference_thumbs
        return clone

    def _fetch_all(self):
        needs_priming = (
            self._prime_reference_thumbs and self._result_cache is None)
        super()._fetch_all()
        if needs_priming:
            prime_reference_thumbs(self._result_cache)


class Thumb(models.Model):

    objects = ThumbQuerySet.as_manager()

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

    def get_url(self, *, image=None, multiplier=1, max_size=False, tmp=False,
                thumbs=None, **opts):
        """Return this crop's URL from the configured renderer."""
        from cropduster.renderers import get_renderer

        return get_renderer().url(
            self, image=image, multiplier=multiplier, max_size=max_size,
            tmp=tmp, thumbs=thumbs, **opts)

    def get_srcset(self, *, densities=(1, 2), image=None, thumbs=None,
                   **opts):
        """Return this crop's ``srcset`` candidates from the configured
        renderer."""
        from cropduster.renderers import get_renderer

        return get_renderer().srcset(
            self, image=image, densities=densities, thumbs=thumbs, **opts)

    @property
    def cache_safe_url(self):
        """A legacy alias for :meth:`get_url`."""
        return self.get_url()

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
                storage = self.image.storage
                with storage.open(tmp_image_path) as tmp_file:
                    with storage.open(image_path, 'wb') as f:
                        f.write(tmp_file.read())
                # delete tmp file
                storage.delete(tmp_image_path)
            except (IOError, OSError):
                pass
        return super(Thumb, self).save(*args, **kwargs)

    def to_dict(self):
        """Returns a dict of the thumb's values which are JSON serializable."""
        dct = {}
        for k, v in vars(self).items():
            if isinstance(v, (str, float, int, bool, type(None))):
                dct[k] = v
        return dct

    def get_crop_box(self):
        """Return this thumb's crop box, or None for an incomplete row."""
        ref_thumb = self.reference_thumb or self
        x1, y1 = ref_thumb.crop_x, ref_thumb.crop_y
        if any([getattr(ref_thumb, 'crop_%s' % a) is None for a in ['x', 'y', 'w', 'h']]):
            return None
        return Box(x1, y1, x1 + ref_thumb.crop_w, y1 + ref_thumb.crop_h)

    def crop(self, original_image=None, size=None, w=None, h=None):
        if original_image is None:
            if not self.pk:
                raise Exception(
                    "The `original_image` argument is required for"
                    " thumbnails which have not yet been saved")

            if not self.image_id:
                raise Exception(
                    "The `original_image` argument is required for"
                    " thumbnails which are not associated with an image")

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
                "Crop box (%dx%d) is too small for resize to (%dx%d)" % (new_w, new_h, width, height))

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


def generate_filename(instance, filename):
    return filename


class ImageQuerySet(models.QuerySet):

    def with_thumbs(self):
        """Prefetch thumbs with sibling references resolved."""
        return self.prefetch_related(
            models.Prefetch(
                'thumbs', Thumb.objects.with_reference_thumbs()))


class Image(models.Model):

    objects = ImageQuerySet.as_manager()

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

    @property
    def storage(self):
        """The storage that contains this image and all of its renditions."""
        return self._meta.get_field('image').storage

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
            return ''
        return os.path.splitext(self.image.name)[1]

    @staticmethod
    def get_file_for_size(image, size_name='original', tmp=False):
        if isinstance(image, str):
            image = VirtualFieldFile(image)
        if not image:
            return None
        path, basename = os.path.split(image.name)
        filename, extension = os.path.splitext(basename)
        if size_name == 'preview':
            size_name = '_preview'
        if tmp:
            size_name = '%s_tmp' % size_name
        return VirtualFieldFile(
            '/'.join([
                path,
                size_name + extension]))

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
                preview_img = im.resize((w, h), PIL.Image.LANCZOS)
            else:
                w, h = orig_w, orig_h
                preview_img = im
            return preview_img

        preview_file = cls.get_file_for_size(image_file, '_preview')
        process_image(pil_img, preview_file.name, fit_preview)
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
        return self.storage.size(self.get_image_path(size_name))

    def get_image_filename(self, size_name='original'):
        size_name = size_name or 'original'
        if size_name != 'original' and not self.has_thumb(size_name):
            return ''
        return os.path.basename(self.get_image_path(size_name))

    def get_image_path(self, size_name='original', tmp=False):
        size_name = size_name or 'original'
        converted = Image.get_file_for_size(self.image, size_name, tmp=tmp)
        if not converted:
            return ''
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

        cropduster_field = get_cropduster_field(
            model_class, field_identifier=self.field_identifier)
        if cropduster_field is not None:
            column_field = get_image_column_field(model_class, cropduster_field)
            if column_field is not None:
                # In multi-table inheritance the column can belong to a
                # parent model, so the update goes through the model that
                # declares it.
                column_field.model.objects.filter(pk=self.object_id).update(
                    **{column_field.attname: self.name or ''})

    def get_image_url(self, size_name='original', tmp=False):
        converted = Image.get_file_for_size(self.image, size_name, tmp=tmp)
        return getattr(converted, 'url', None) or ''

    def get_url(self, size_name='original', **opts):
        """Return an original, preview, or named crop URL from the renderer."""
        from cropduster.renderers import get_renderer

        renderer = get_renderer()
        size_name = size_name or 'original'
        if size_name == 'original':
            return renderer.original_url(self, **opts)
        if size_name == 'preview':
            return renderer.preview_url(self, **opts)
        thumbs = list(self.thumbs.all())
        for thumb in thumbs:
            if thumb.name == size_name:
                return renderer.url(
                    thumb, image=self, thumbs=thumbs, **opts)
        return None

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
        if not self.image or not self.storage.exists(self.image.name):
            return (0, 0)
        elif self.width and self.height:
            return (self.width, self.height)
        else:
            try:
                with self.image_file_open() as f:
                    img = PIL.Image.open(BytesIO(f.read()))
                    img.filename = f.name
            except (IOError, ValueError, TypeError):
                return (0, 0)
            else:
                return img.size

    def delete(self, *args, **kwargs):
        obj = self.content_object
        image_name = self.image.name if (self.image) else None
        field_identifier = self.field_identifier

        super(Image, self).delete(*args, **kwargs)

        if not obj or not image_name:
            return

        cropduster_field = get_cropduster_field(
            type(obj), field_identifier=field_identifier)
        if cropduster_field is None:
            return
        column_field = get_image_column_field(type(obj), cropduster_field)
        if column_field is None:
            return
        obj_image_name = getattr(
            getattr(obj, column_field.name, None), 'name', None)
        if obj_image_name != image_name:
            return

        # obj can hold stale values for its other fields, so the column is
        # cleared with a queryset update() instead of obj.save(). In
        # multi-table inheritance the column can belong to a parent model.
        column_field.model._default_manager.filter(pk=obj.pk).update(
            **{column_field.attname: ''})
        setattr(obj, column_field.name, '')

    def save_size(self, size, thumb=None, image=None, tmp=False, standalone=False,
                  permissive=False, skip_existing=False, commit=True):
        thumbs = {}
        if not image and not self.image:
            raise Exception("Cannot save sizes without an image")

        if not image:
            with self.image_file_open() as f:
                image = PIL.Image.open(BytesIO(f.read()))
                image.filename = f.name

        if standalone:
            require_standalone()
            return self._save_standalone_thumb(size, image, thumb, commit=commit)

        for sz in Size.flatten([size]):
            if (self.pk and skip_existing
                    and self.storage.exists(self.get_image_path(sz.name))):
                try:
                    existing_thumb = self.thumbs.get(name=sz.name)
                except Thumb.DoesNotExist:
                    pass
                else:
                    thumbs[sz.name] = existing_thumb
                    continue
            try:
                if thumb and sz.is_auto:
                    new_thumb = self._save_thumb(
                        sz, image, ref_thumb=thumb, tmp=tmp, commit=commit)
                else:
                    thumb = new_thumb = self._save_thumb(sz, image, thumb, tmp=tmp, commit=commit)
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

    def _save_standalone_thumb(self, size, image=None, thumb=None, commit=True):
        if not thumb:
            thumb = Thumb(
                width=self.width, height=self.height,
                crop_x=0, crop_y=0, crop_w=self.width, crop_h=self.height)
        thumb.name = ''.join([random.choice('abcdefghijklmnopqrstuvwxyz0123456789') for i in range(0, 8)])
        thumb_path = self.get_image_path(thumb.name)

        # In standalone mode, if only one dimension is overridden by the user,
        # ensure the other matches the crop-box aspect ratio
        w, h = size.w, size.h
        aspect_ratio = float(thumb.crop_w) / float(thumb.crop_h)
        if w and not h:
            h = int(round(w / aspect_ratio))
        elif h and not w:
            w = int(round(h * aspect_ratio))

        thumb_crop = thumb.crop(image, size, w=w, h=h)
        thumb_image = thumb_crop.create_image(thumb_path, width=thumb.width, height=thumb.height)
        thumb_image.crop.add_xmp_to_crop(thumb_path, size, original_image=image)
        md5 = hashlib.md5()
        with self.storage.open(thumb_path, mode='rb') as f:
            image_contents = f.read()
        md5.update(image_contents)
        thumb.name = md5.hexdigest()[0:9]
        new_path = self.get_image_path(thumb.name)
        with self.storage.open(new_path, 'wb') as f:
            f.write(image_contents)
        self.storage.delete(thumb_path)

        if not thumb.pk:
            try:
                thumb.id = Thumb.objects.get(image=self, name=thumb.name).pk
            except Thumb.DoesNotExist:
                pass

        thumb.image = self

        if commit:
            thumb.save()

        return thumb

    def image_file_open(self):
        return self.storage.open(self.image.name, 'rb')

    def _save_thumb(self, size, image=None, thumb=None, ref_thumb=None, tmp=False, commit=True):
        if not image:
            with self.image_file_open() as f:
                image = PIL.Image.open(BytesIO(f.read()))
                image.filename = f.name
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

        if cropduster_settings.CROPDUSTER_CREATE_THUMBS:
            thumb_image = thumb_crop.create_image(thumb_path, width=thumb.width, height=thumb.height)

        if cropduster_settings.CROPDUSTER_CREATE_THUMBS:
            thumb_image.crop.add_xmp_to_crop(thumb_path, size, original_image=image)

        if commit:
            thumb.save()
        return thumb


# Re-exported for ``from cropduster.models import StandaloneImage``. Only the
# metadata module needs libxmp, so the model is registered with or without
# the optional standalone dependencies.
from cropduster.standalone.models import StandaloneImage  # noqa: E402
