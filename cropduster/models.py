from django.core.exceptions import ValidationError
from django.db import models
from django.conf import settings
import uuid
import os
from cropduster import utils
from PIL import Image as pil

IMAGE_SAVE_PARAMS =  {"quality" :95}

try:
    from caching.base import CachingMixin, CachingManager
except ImportError:
    class CachingMixin(object):
        pass
    CachingManager = models.Manager

nearest_int = lambda a: int(round(a))
to_retina_path = lambda p: '%s@2x%s' % os.path.splitext(p)
class ImageSizeSet(CachingMixin, models.Model):
    class Meta:
        db_table = 'cropduster_sizeset'

    objects = CachingManager()
    name = models.CharField(max_length=255, db_index=True)
    slug = models.SlugField(max_length=50, null=False, unique=True)
    
    def __unicode__(self):
        return u"%s" % self.name
        
    def get_size_by_ratio(self):
        """ Shorthand to get all the unique ratios for display in the admin, 
        rather than show every possible thumbnail
        """
        
        size_query = Size.objects.all().filter(size_set__id=self.id)
        size_query.query.group_by = ["aspect_ratio"]
        try:
            return size_query
        except ValueError:
            return None
            
class ImageSize(CachingMixin, models.Model):
    
    class Meta:
        db_table = "cropduster_size"
    
    # An ImageSize not associated with a set is a 'one off'
    size_set = models.ForeignKey(ImageSizeSet, null=True)
    
    date_modified = models.DateTimeField(auto_now=True)

    name = models.CharField(max_length=255, db_index=True)
    
    slug = models.SlugField(max_length=50, null=False)
    
    height = models.PositiveIntegerField(null=True)
    
    width = models.PositiveIntegerField(null=True)
    
    aspect_ratio = models.FloatField(null=True)

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
        return (self.get_width(), self.get_height(), self.aspect_ratio)

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
            return w, h

        # Empty sizes are basically useless.
        if not (w or h):
            return width, height

        aspect_ratio = round(width/float(height), 2)
        if w: 
            h = nearest_int(w / aspect_ratio)
        else:
            w = nearest_int(h * aspect_ratio)

        return w, h

    def __unicode__(self):
        return u"%s: %sx%s" % (self.name, self.width, self.height)

class Crop(CachingMixin, models.Model):
    class Meta:
        db_table = "cropduster_crop"
        
    objects = CachingManager()
        
    crop_x = models.PositiveIntegerField(default=0, blank=True, null=True)
    crop_y = models.PositiveIntegerField(default=0, blank=True, null=True)
    crop_w = models.PositiveIntegerField(default=0, blank=True, null=True)
    crop_h = models.PositiveIntegerField(default=0, blank=True, null=True)
    
    def __unicode__(self):
        return u"Crop: (%i, %i)(%i, %i) " % ( self.crop_x,
                                              self.crop_y,
                                              self.crop_x + self.crop_w,
                                              self.crop_y + self.crop_h)

class Image(CachingMixin, models.Model):
    
    objects = CachingManager()

    class Meta:
        db_table = "cropduster_image"
        verbose_name = "Image"
        verbose_name_plural = "Image"

    # Original image if this is generated from another image.
    original = models.ForeignKey('self',
                                 related_name='derived',
                                 null=True)

    image = models.ImageField(
        upload_to=settings.CROPDUSTER_UPLOAD_PATH + "%Y/%m/%d", 
        width_field='width',
        height_field='height',
        max_length=255)

    # An image doesn't need to have a size associated with it, only
    # if we want to transform it.
    size = models.ForeignKey(ImageSize, null=True)
    crop = models.ForeignKey(Crop, null=True)

    # Image can have 0:N size-sets
    size_sets = models.ManyToManyField(ImageSizeSet, null=True)

    date_modified = models.DateTimeField(auto_now=True)

    # Attribution details.
    attribution = models.CharField(max_length=255, blank=True, null=True)
    caption = models.CharField(max_length=255, blank=True, null=True)

    width = models.PositiveIntegerField(null=True)
    height = models.PositiveIntegerField(null=True)
    
    @property
    def retina_path(self):
        """
        Returns the path to the retina image if it exists.
        """
        return '%s@2x%s' % os.path.splitext(self.image.path)

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
            size_set = ImageSizeSet.objects.get(**kwargs)

        self.size_sets.add( size_set )

        # Do not duplicate images which are already in the
        # derived set.
        d_ids = set(d.size.id for d in self.derived.all())

        # Create new derived images from the size set
        return [self.new_derived_image(size=size) 
                    for size in size_set.imagesize_set.all()
                        if size.id not in d_ids]

    def new_derived_image(self, **kwargs):
        """
        Creates a new derived image from the current image.

        @return: new Image
        @rtype: Image
        """
        return Image(original=self, **kwargs)

    def _save_to_tmp(self, image):
        """
        Saves an image to a tempfile.

        @param image: Image to save.
        @type  image: 

        @return: 
        @rtype: 
        """
        path = self._get_tmp_img_path()
        utils.save_image(image, path)
        return path

    def render(self, force=False):
        """
        Renders an image according to its Crop and its Size.  If the size
        also specifies a retina image, it will attempt to render that as well.
        If a crop is set, it is applied to the image before any resizing happens.

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
        # We really only want to do rescalings on derived images, but
        # we don't prevent people from it.
        image_path = self.original.image.path if self.original else self.image.path 

        if not (self.crop or self.size):
            # Nothing to do.
            return


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
            orig_width, orig_height = image.size
            width, height = self.size.calc_dimensions(orig_width, orig_height)

            if self.size.retina:
                # If we are supposed to build a retina, make sure the 
                # dimensions are large enough.  No stretching allowed
                # for retina.
                self._new_retina = None
                if orig_width >= width*2 and orig_height >= height*2:
                    retina = utils.rescale(image.copy(),
                                           width*2,
                                           height*2,
                                           self.size.auto_crop)

                    self._new_retina = self._save_to_tmp(retina)

            # Calculate the main image
            image = utils.rescale(image,
                                  width,
                                  height,
                                  self.size.auto_crop)

        # Save the image in a temporary place
        self._new_image = self._save_to_tmp(image)

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
        if hasattr(settings,'CROPDUSTER_TMP_DIR'):
            tmp_path = settings.CROPDUSTER_TMP_DIR
        else:
            tmp_path = os.path.dirname(dest_path)

        ext = os.path.splitext(dest_path)[1]
            
        return os.path.join(tmp_path, uuid.uuid4().hex+ext)

    def get_dest_img_path(self):
        """
        Figures out where to place save a new image for this Image.

        @return: path to image location
        @rtype: "/path/to/image"
        """
        # If we have a path already, reuse it.
        if self.image:
            return self.image.path
            
        # Calculate it from the size slug if possible.
        orig_path = self.original.image.path
        if self.size:
            slug = self.size.slug

        elif self.crop:
            slug = os.path.splitext(os.path.basename(orig_path))[0]
        else:
            # Guess we have to return the original path
            return orig_path

        # Remove the extension
        path, ext = os.path.splitext(orig_path)
        return os.path.join(path, slug) + ext
        
    def has_size(self, size_slug):
        return self.derived.filter(size__slug=size_slug).count() > 0

    def set_crop(self, x, y, width, height):
        """
        Sets the crop size for an image.  It should be noted that the crop
        object is NOT saved by default, so should be saved manually.

        Adds a croping ruling from top-left (x,y) to bottom-right (x+width, y+width).

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
        return unicode(self.image.url) if self.image else u""
            
    def get_absolute_url(self):
        """
        Returns the abolute url to the image.

        @return: 
        @rtype: 
        """
        return os.path.join(settings.STATIC_URL, self.image.url)

    def save(self, *args, **kwargs):
        # Do we have a new image?  If so, we need to move it over.
        if getattr(self, '_new_image', None) is not None:
            path = self.get_dest_img_path()
            os.rename(self._new_image, path)
            self.image = path
            del self._new_image

            # Check for a new retina
            if hasattr(self, '_new_retina'):
                retina_path = to_retina_path(path)
                if self._new_retina is None: 
                    if os.path.exists(retina_path):
                        # If the reina is now invalid, remove the previous one.
                        os.unlink(retina_path)
                else:
                    os.rename(self._new_retina, retina_path)

                del self._new_retina

        return super(Image, self).save(*args, **kwargs)

    def get_descendents(self):
        """
        Gets all descendants for the current image.
        """
        stack = [self]
        while stack:
            children = stack.pop().derived.all()
            for c in children:
                yield c

            stack.extend(descendents)

    def delete(self, *args, **kwargs):
        # Delete manual image sizes.
        if self.size is not None and self.size.size_set is None:
            self.size.delete()

        # All crops are unique to the image.
        if self.crop is not None:
            self.crop.delete()

        return super(Image, self).delete(*args, **kwargs)

class CropDusterField(models.ForeignKey):
    pass    

try:
    from south.modelsinspector import add_introspection_rules
except ImportError:
    pass
else:
    add_introspection_rules([], ["^cropduster\.models\.CropDusterField"])
