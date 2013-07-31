import re
import shutil
import time
import uuid
import os
import datetime
import hashlib
import itertools
import urllib

from PIL import Image as pil

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.fields.related import ReverseSingleRelatedObjectDescriptor
from django.conf import settings
from django.db.models.signals import post_save

from . import utils
from . import settings as cropduster_settings

try:
    from caching.base import CachingMixin, CachingManager
except ImportError:
    class CachingMixin(object):
        pass
    CachingManager = models.Manager

assert not settings.CROPDUSTER_UPLOAD_PATH.startswith('/')

nearest_int = lambda a: int(round(a))
to_retina_path = lambda p: '%s@2x%s' % os.path.splitext(p)

class SizeSet(CachingMixin, models.Model):

    objects = CachingManager()

    class Meta:
        app_label = cropduster_settings.CROPDUSTER_APP_LABEL
        db_table = '%s_sizeset' % cropduster_settings.CROPDUSTER_DB_PREFIX

    name = models.CharField(max_length=255, db_index=True)
    slug = models.SlugField(max_length=50, null=False, unique=True)

    def __unicode__(self):
        return u"%s" % self.name

    def get_size_by_ratio(self):
        """ Shorthand to get all the unique ratios for display in the admin,
        rather than show every possible thumbnail
        """

        size_query = Size.objects.filter(size_set__id=self.id)
        size_query.query.group_by = ["aspect_ratio"]
        try:
            return size_query
        except ValueError:
            return None

class Size(CachingMixin, models.Model):

    objects = CachingManager()

    class Meta:
        app_label = cropduster_settings.CROPDUSTER_APP_LABEL
        db_table = '%s_size' % cropduster_settings.CROPDUSTER_DB_PREFIX

    # An Size not associated with a set is a 'one off'
    size_set = models.ForeignKey(SizeSet, null=True)
    
    date_modified = models.DateTimeField(auto_now=True, null=True)

    name = models.CharField(max_length=255, db_index=True)

    slug = models.SlugField(max_length=50, null=False)

    height = models.PositiveIntegerField(null=True, blank=True)

    width = models.PositiveIntegerField(null=True, blank=True)

    aspect_ratio = models.FloatField(null=True, blank=True)

    auto_crop = models.BooleanField(default=False)

    retina = models.BooleanField(default=False)

    def get_height(self):
        """
        Return calculated height, if possible.

        @return: Height
        @rtype: positive int
        """
        if self.height is None and self.width and self.aspect_ratio:
            return nearest_int(self.width / self.aspect_ratio)

        return self.height

    def get_width(self):
        """
        Returns calculate width, if possible.

        @return: Width
        @rtype: positive int
        """
        if self.width is None and self.height and self.aspect_ratio:
            return nearest_int(self.height * self.aspect_ratio)

        return self.width

    def get_aspect_ratio(self):
        """
        Returns calculated aspect ratio, if possible.

        @return: Aspect Ratio
        @rtype:  float
        """
        if self.aspect_ratio is None and self.height and self.width:
            return round(self.width / float(self.height), 2)

        return self.aspect_ratio

    def get_dimensions(self):
        """
        Returns all calculated dimensions for the size.

        @return: width, height, aspect ratio
        @rtype: (int > 0, int > 0, float > 0)
        """
        return (self.get_width(), self.get_height(), self.get_aspect_ratio())

    def calc_dimensions(self, width, height):
        """
        From a given set of dimensions, calculates the rendered size.

        @param width: Starting width
        @type  width: Positive int

        @param height: Starting height
        @type  height: Positive int

        @return: rendered width, rendered height
        @rtype: (Width, Height)
        """
        w, h, a = self.get_dimensions()
        # Explicit dimension give explicit answers
        if w and h:
            return w, h, a

        # Empty sizes are basically useless.
        if not (w or h):
            return width, height, None

        aspect_ratio = round(width / float(height), 2)
        if w:
            h = nearest_int(w / aspect_ratio)
        else:
            w = nearest_int(h * aspect_ratio)

        return w, h, round(w / float(h), 2)

    def __unicode__(self):
        return u"%s: %sx%s" % (self.name, self.width, self.height)

    def save(self, *args, **kwargs):
        if self.slug is None:
            self.slug = uuid.uuid4().hex
        w, h, a = self.get_dimensions()
        self.width = w
        self.height = h
        self.aspect_ratio = a
        super(Size, self).save(*args, **kwargs)


class Crop(CachingMixin, models.Model):

    class Meta:
        app_label = cropduster_settings.CROPDUSTER_APP_LABEL
        db_table = '%s_crop' % cropduster_settings.CROPDUSTER_DB_PREFIX

    objects = CachingManager()

    crop_x = models.PositiveIntegerField(default=0, blank=True, null=True)
    crop_y = models.PositiveIntegerField(default=0, blank=True, null=True)
    crop_w = models.PositiveIntegerField(default=0, blank=True, null=True)
    crop_h = models.PositiveIntegerField(default=0, blank=True, null=True)

    def __unicode__(self):
        return u"Crop: (%i, %i),(%i, %i) " % (
            self.crop_x,
            self.crop_y,
            self.crop_x + self.crop_w,
            self.crop_y + self.crop_h,
        )


class ImageMetadata(CachingMixin, models.Model):

    objects = CachingManager()

    class Meta:
        app_label = cropduster_settings.CROPDUSTER_APP_LABEL
        db_table = '%s_image_meta' % cropduster_settings.CROPDUSTER_DB_PREFIX

    # Attribution details.
    attribution = models.CharField(max_length=255, blank=True, null=True)
    attribution_link = models.URLField(max_length=255, blank=True, null=True)
    caption = models.CharField(max_length=255, blank=True, null=True)

class Image(CachingMixin, models.Model):

    objects = CachingManager()

    class Meta:
        app_label = cropduster_settings.CROPDUSTER_APP_LABEL
        db_table = '%s_image' % cropduster_settings.CROPDUSTER_DB_PREFIX
        verbose_name = "Image"
        verbose_name_plural = "Image"

    # Original image if this is generated from another image.
    original = models.ForeignKey('self',
                                 related_name='derived',
                                 null=True)

    image = models.ImageField(
        upload_to=lambda obj, filename: obj.cropduster_upload_to(filename),
        width_field='width',
        height_field='height',
        max_length=255)

    # An image doesn't need to have a size associated with it, only
    # if we want to transform it.
    size = models.ForeignKey(Size, null=True)
    crop = models.OneToOneField(Crop, null=True)

    # Image can have 0:N size-sets
    size_sets = models.ManyToManyField(SizeSet, null=True)

    # Single set of attributions
    metadata = models.ForeignKey(ImageMetadata, null=True, blank=True)

    date_modified = models.DateTimeField(auto_now=True, null=True)

    width = models.PositiveIntegerField(null=True)
    height = models.PositiveIntegerField(null=True)

    @staticmethod
    def cropduster_upload_to(filename, fmt="%Y/%m/%d"):
        if fmt:
            now = datetime.date.today()
            fmt = now.strftime(fmt)
        else:
            fmt = ''
        return os.path.join(settings.CROPDUSTER_UPLOAD_PATH, fmt, filename)

    @property
    def retina_path(self):
        """
        Returns the path to the retina image if it exists.
        """
        return to_retina_path(self.image.path)

    @property
    def aspect_ratio(self):
        if self.width and self.height:
            return round(self.width / float(self.height), 2)
        return None

    @property
    def is_original(self):
        return self.original is None

    def add_size_set(self, size_set=None, **kwargs):
        """
        Adds a size set to the current image.  If the sizeset
        is provided, will add that otherwise it will query
        all size sets that match the **kwarg criteria

        @return: Newly created derived images from size set.
        @rtype:  [Image1, ...]
        """
        if size_set is None:
            size_set = SizeSet.objects.get(**kwargs)

        self.size_sets.add(size_set)

        # Do not duplicate images which are already in the
        # derived set.
        d_ids = set(d.size.id for d in self.derived.all())

        # Create new derived images from the size set
        return [self.new_derived_image(size=size)
                    for size in size_set.size_set.all()
                        if size.id not in d_ids]

    def get_metadata(self):
        if self.metadata is None:
            if self.original is not None:
                metadata = self.original.get_metadata()
            else:
                metadata = ImageMetadata()

            self.metadata = metadata
        return self.metadata

    def new_derived_image(self, **kwargs):
        """
        Creates a new derived image from the current image.

        @return: new Image
        @rtype: Image
        """
        return Image(original=self, metadata=self.get_metadata(), **kwargs)

    def set_manual_size(self, **kwargs):
        """
        Sets a manual size on the image.

        @return: New Size object, unsaved
        @rtype: @{Size}
        """
        # If we don't have a size or we have a size from a size set,
        # we need to create a new Size object.
        if self.size is None or self.size.size_set is not None:
            self.size = Size(**kwargs)
        else:
            # Otherwise, update the values
            for k, v in kwargs.iteritems():
                setattr(self.size, k, v)

        return self.size

    def _save_to_tmp(self, image):
        """
        Saves an image to a tempfile.

        @param image: Image to save.
        @type  image:

        @return: Temporary path where the image is saved.
        @rtype:  /path/to/file
        """
        path = self._get_tmp_img_path()
        return utils.save_image(image, path)

    def render(self, force=False):
        """
        Renders an image according to its Crop and its Size.  If the size also
        specifies a retina image, it will attempt to render that as well. If a
        crop is set, it is applied to the image before any resizing happens.

        By default, render will throw an error if an attempt is made to render
        an original image.

        NOTE: While render will create a new image, it will be stored it in a
        temp file until the object is saved when it will overwrite the
        previously stored image.  There are a couple of reasons for this:

        1. If there's any sort of error, the previous image is preserved,
           making re-renderings of images safe.

        2. We have to resave the image anyways since 'width' and 'height' have
           likely changed.

        3. If for some reason we want to 'rollback' a change, we don't have
           to do anything special.

        The temporary images are saved in CROPDUSTER_TMP_DIR if available, or
        falls back to the directory the image currently resides in.

        @param force: If force is True, render will allow overwriting the
                      original image.
        @type  force:  bool.
        """
        if not force and self.is_original:
            raise ValidationError("Cannot render over an original image.  "\
                                  "Use render(force=True) to override.")

        if not (self.crop or self.size):
            # Nothing to do.
            return

        # We really only want to do rescalings on derived images, but
        # we don't prevent people from it.
        if self.original:
            image_path = self.original.image.path
        else:
            image_path = self.image.path

        if self.crop:
            image = utils.create_cropped_image(image_path,
                self.crop.crop_x,
                self.crop.crop_y,
                self.crop.crop_w,
                self.crop.crop_h)
        else:
            image = pil.open(image_path)

        # If we are resizing the image.
        if self.size:
            size = self.size
            orig_width, orig_height = image.size
            width, height = size.calc_dimensions(orig_width, orig_height)[:2]

            if size.retina:
                # If we are supposed to build a retina, make sure the
                # dimensions are large enough.  No stretching allowed!
                self._new_retina = None
                if orig_width >= (width * 2) and orig_height >= (height * 2):
                    retina = utils.rescale(utils.copy_image(image),
                        width * 2, height * 2, size.auto_crop)
                    self._new_retina, _fmt = self._save_to_tmp(retina)

            # Calculate the main image
            image = utils.rescale(image, width, height, size.auto_crop)

        # Save the image in a temporary place
        self._new_image, self._new_image_format = self._save_to_tmp(image)

    def _get_tmp_img_path(self):
        """
        Returns a temporary image path.  We should probably be using the
        Storage objects, but this works for now.

        Tries to it in CROPDUSTER_TMP_DIR if set, falls back to the current
        directory of the image.

        @return: Temporary image location.
        @rtype:  "/path/to/file"
        """
        dest_path = self.get_dest_img_path()
        if hasattr(settings, 'CROPDUSTER_TMP_DIR'):
            tmp_path = settings.CROPDUSTER_TMP_DIR
        else:
            tmp_path = os.path.dirname(dest_path)

        ext = os.path.splitext(dest_path)[1]

        return os.path.join(tmp_path, uuid.uuid4().hex + ext)

    def get_dest_img_path(self):
        """
        Figures out where to place save a new image for this Image.

        @return: path to image location
        @rtype: "/path/to/image"
        """
        # If we have a path already, reuse it.
        if self.image:
            return self.image.path

        return self.get_dest_img_from_base(self.original.image.path)

    def get_dest_img_name(self):
        if self.image:
            return self.image.name
        return self.get_dest_img_from_base(self.original.image.name)

    def get_dest_img_from_base(self, base):
        # Calculate it from the size slug if possible.
        if self.size:
            slug = self.size.slug
        elif self.crop:
            slug = os.path.splitext(os.path.basename(base))[0]
        else:
            # Guess we have to return the original path
            return base

        path, ext = os.path.splitext(base)
        return os.path.join(path, slug) + ext

    def has_size(self, size_slug):
        return self.derived.filter(size__slug=size_slug).count() > 0

    def set_crop(self, x, y, width, height):
        """
        Sets the crop size for an image.  It should be noted that the crop
        object is NOT saved by default, so should be saved manually.

        Adds a crop from top-left (x,y) to bottom-right (x+width, y+width).

        @return: The unsaved crop object.
        @rtype: {Crop}
        """
        if self.crop is None:
            self.crop = Crop()

        self.crop.crop_x = x
        self.crop.crop_y = y
        self.crop.crop_w = width
        self.crop.crop_h = height
        return self.crop

    def __unicode__(self):
        return self.get_absolute_url() if self.image else u""

    def get_absolute_url(self, date_hash=True):
        """
        Gets the absolute url for an image.

        @param date_hash: If True, adds a GET param hex hash indicating
                          the update date for the image.
        @type  date_hash: bool

        @return: Absolute path to the url
        @rtype: basestring
        """
        path = self.image.url
        if date_hash:
            unix_time = int(time.mktime(self.date_modified.timetuple()))
            path += '?' + format(unix_time, 'x')

        # Django's filepath_to_uri passes '()' in the safe kwarg to
        # urllib.quote, which is problematic when used in inline
        # background-image:url() styles.
        # This regex replaces '(' and ')' with '%28' and '%29', respectively
        url = unicode(path)
        return re.sub(r'([\(\)])', lambda m: urllib.quote(m.group(1)), url)

    def get_thumbnail(self, slug, size_set=None):
        """
        Returns the derived image for the Image or None if it does not exist.

        @param slug: Name of the image slug.
        @type  slug: basestring

        @param size_set: Size Set object to filter by, if available.
        @type  size_set: SizeSet.

        @return: Image or None
        @rtype: Image or None
        """
        try:
            if size_set:
                return self.derived.get(size__size_set=size_set, size__slug=slug)
            else:
                return self.derived.filter(size__slug=slug)[0]
        except IndexError:
            return None
        except Image.DoesNotExist:
            return None

    def __init__(self, *args, **kwargs):
        if 'metadata' not in kwargs and 'metadata_id' not in kwargs:
            kwargs['metadata'] = ImageMetadata()

        return super(Image, self).__init__(*args, **kwargs)

    def save(self, *args, **kwargs):
        # Make sure our original image is saved
        if self.original and not self.original.pk:
            self.original.save()

        # Make sure we've saved our metadata
        metadata = self.get_metadata()
        if not metadata.id:
            metadata.save()

            # Bug #8892, not updating the 'metadata_id' field.
            self.metadata = metadata

        # Do we have a new image?  If so, we need to move it over.
        if getattr(self, '_new_image', None) is not None:

            name = self.get_dest_img_name()
            if getattr(settings, 'CROPDUSTER_NORMALIZE_EXT', False):
                if not name.endswith(self._new_image_format.lower()):
                    rest, _ext = os.path.splitext(name)
                    name = rest + '.' + self._new_image_format.lower()

            # Since we only store relative paths in here, but want to get
            # the correct absolute path, we have to set the image name first
            # before we set the image directly (which will)
            self.image.name = name
            os.rename(self._new_image, self.image.path)
            self.image = name

            # I'm not a fan of all this state, but it needs to be saved
            # somewhere.
            del self._new_image
            del self._new_image_format

            # Check for a new retina
            if hasattr(self, '_new_retina'):
                retina_path = self.retina_path
                if self._new_retina is None:
                    if os.path.exists(retina_path):
                        # If the reina is now invalid, remove the previous one.
                        os.unlink(retina_path)
                else:
                    os.rename(self._new_retina, retina_path)

                del self._new_retina

        return super(Image, self).save(*args, **kwargs)

    @property
    def descendants(self):
        """
        Gets all descendants for the current image, starting at the highest
        levels and recursing down.

        @returns set of descendants
        @rtype  <Image1, ...>
        """
        stack = [self]
        while stack:
            original = stack.pop()
            children = original.derived.all()
            for c in children:
                c.original = original
                yield c

            stack.extend(children)

    @property
    def ancestors(self):
        """
        Returns the set of ancestors associated with an Image
        """
        current = self
        while current.original:
            yield current.original
            current = current.original

    def delete(self, remove_images=True, *args, **kwargs):
        """
        Deletes an image, attempting to clean up foreign keys as well.

        @param remove_images: If True, performs a bulk delete and then
                              deletes all derived images.  It does not,
                              however, remove the directories.
        @type  remove_images: bool
        """
        # Delete manual image sizes.
        if self.size is not None and self.size.size_set is None:
            self.size.delete()

        # All crops are unique to the image.
        if self.crop is not None:
            self.crop.delete()

        return super(Image, self).delete(*args, **kwargs)

class CropDusterReverseProxyDescriptor(ReverseSingleRelatedObjectDescriptor):

    def __set__(self, instance, value):
        if value is not None and not isinstance(value, self.field.rel.to):
            # ok, are we a direct subclass?
            mro = self.field.rel.to.__mro__
            if len(mro) > 1 and type(value) == mro[1]: 
                # Convert to the appropriate proxy object
                value.__class__ = self.field.rel.to

        super(CropDusterReverseProxyDescriptor, self).__set__(instance, value)

PROXY_COUNT = itertools.count(1)
class CropDusterField(models.ForeignKey):
    dynamic_path = False
    def __init__(self, upload_to=None,  dynamic_path=False, *args, **kwargs):
        if upload_to is None:
            if not args and 'to' not in kwargs:
                args = (Image,)
            super(CropDusterField, self).__init__(*args, **kwargs)
            return

        # Figure out what we are inheriting from.
        if args and issubclass(args[0], Image):
            base_cls = args[0]
            args = tuple(args[1:])
        elif 'to' in kwargs and issubclass(kwargs.get('to'), Image): 
            base_cls = kwargs.get('to')
        else:
            base_cls = Image

        if callable(upload_to) and dynamic_path:
            # we have a function and we want it to dynamically change
            # based on the instance
            self.dynamic_path = True

        if isinstance(upload_to, basestring):
            upload_path = upload_to
            def upload_to(object, filename):
                return Image.cropduster_upload_to(filename, upload_path)

        elif callable(upload_to):
            old_upload_to = upload_to
            def upload_to(self, filename, instance=None):
                new_path = old_upload_to(filename, instance)
                return os.path.join(settings.CROPDUSTER_UPLOAD_PATH, new_path)
        else:
            raise TypeError("'upload_to' needs to be either a callable or string")

        # We have to create a unique class name for each custom proxy image otherwise
        # django likes to alias them together.
        ProxyImage = type('ProxyImage%i' % next(PROXY_COUNT), 
                          (base_cls,),
                          {'Meta': type('Meta', (), {'proxy':True}),
                           'cropduster_upload_to': upload_to,
                           '__module__': Image.__module__})

        return super(CropDusterField, self).__init__(ProxyImage, *args, **kwargs)
    
    def contribute_to_class(self, cls, name):
        super(CropDusterField, self).contribute_to_class(cls, name)
        setattr(cls, self.name, CropDusterReverseProxyDescriptor(self))
        
        if self.dynamic_path: 
            def post_signal(sender, instance, created, *args, **kwargs):
                cdf = getattr(instance, name, None)
                if cdf is not None:
                    dynamic_path_save(instance, cdf)

            post_save.connect(post_signal, sender=cls, weak=False)

def dynamic_path_save(instance, cdf):
    # Ok, try to move the fields.
    if cdf is None:
        # No image to check, move along.
        return

    # Check to see if the paths are the same
    old_name = cdf.image.name
    basename = os.path.basename(old_name)
    new_name  = cdf.cropduster_upload_to(basename, instance=instance)
    if new_name == old_name:
        # Nothing to move, move along
        return

    old_to_new = {}
    old_path = cdf.image.path
    images = [cdf]
    cdf.image.name = new_name
    old_to_new[old_path] = cdf.image.path

    # Iterate through all derived images, updating the paths
    for derived in cdf.descendants:

        old_path = derived.image.path
        old_retina_path = derived.retina_path

        # Update the name to the new one
        derived.image.name = derived.get_dest_img_from_base(derived.original.image.name)
        old_to_new[old_path] = derived.image.path

        # Only add the retina if it exists.
        if os.path.exists(old_retina_path) and derived.size.retina:
            old_to_new[old_retina_path] = derived.retina_path

        images.append(derived)

    # Filter out paths which haven't changed.
    old_to_new = dict((k,v) for k,v in old_to_new.iteritems() if k != v)

    # Copy the images... this is not cheap
    for old_path, new_path in old_to_new.iteritems():
        # Create the directory, if needed
        dirname = os.path.dirname(new_path)
        if not os.path.isdir(dirname):
            if os.path.exists(dirname):
                raise ValidationError("Cannot create new directory '%s'" % dirname)

            os.makedirs(dirname)

        # Copy the file, should blow up for all manner of things.
        shutil.copy(old_path, new_path)

        # Check existance
        if not os.path.exists(new_path):
            raise ValidationError("Could not copy image %s to %s" % (old_path, new_path))

    # Save the images
    for image in images:
        image.save()

    # Ok, we've made every reasonable attempt to preserve data... delete!
    old_dirs = set()
    for old_path in old_to_new:
        os.unlink(old_path)
        old_dirs.add( os.path.dirname(old_path) )

    # Files are deleted, delete empty directories, except the upload path... 
    # that would be bad
    for path in reversed(sorted(old_dirs, key=lambda d: d.count('/'))):
        if not os.listdir(path) and path not in settings.MEDIA_ROOT:
            os.rmdir(path)

class ImageRegistry(object):
    """
    Registers cropduster Images to a hash to make it reasonable to lookup
    image directly from the admin.
    """
    hashes = {}
    @classmethod
    def add(cls, model, field_name, Image):
        model_hash = hashlib.md5('%s:%s' % (model, field_name)).hexdigest()
        cls.hashes[model_hash] = Image
        return model_hash

    @classmethod
    def get(cls, image_hash):
        return cls.hashes.get(image_hash, Image)

try:
    from south.modelsinspector import add_introspection_rules
except ImportError:
    pass
else:
    add_introspection_rules([], ["^cropduster3\.models\.CropDusterField"])
