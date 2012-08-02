from django.db import models
from django.conf import settings
import os, copy
from cropduster import utils
from PIL import Image as pil
from south.modelsinspector import add_introspection_rules
from django.core.exceptions import ValidationError


CROPDUSTER_UPLOAD_PATH = getattr(settings, "CROPDUSTER_UPLOAD_PATH", settings.MEDIA_ROOT)

IMAGE_SAVE_PARAMS =  {"quality" :95}

MANUALLY_CROP = 0
AUTO_CROP = 1
AUTO_SIZE = 2

GENERATION_CHOICES = (
	(MANUALLY_CROP, "Manually Crop"),
	(AUTO_CROP, "Auto-Crop"),
	(AUTO_SIZE, "Auto-Size"),
)

RETINA_POSTFIX = "@2x"

try:
	from caching.base import CachingMixin, CachingManager
except ImportError:
	class CachingMixin(object):
		pass
	CachingManager = models.Manager

class SizeSet(CachingMixin, models.Model):
	objects = CachingManager()
	
	name = models.CharField(max_length=255, db_index=True)
	
	slug = models.SlugField(max_length=50, null=False,)
	
	def __unicode__(self):
		return u"%s" % self.name
		
	def get_unique_ratios(self, created=True):
		""" 
			Shorthand to get all the unique ratios rather than show every possible thumbnail
		"""
		create_on_request =  not created
		
		size_query = Size.objects.all().filter(size_set__id=self.id, create_on_request=create_on_request)
		
		size_query.query.group_by = ["aspect_ratio"]
		try:
			return size_query
		except ValueError:
			return None


class SizeManager(CachingManager):
	def get_size_by_ratio(self, size_set, aspect_ratio_id):
		""" Gets the largest image of a certain ratio in this size set """
		
		size_query = Size.objects.all().only("aspect_ratio").filter(size_set=size_set, auto_size=0).order_by("-aspect_ratio")
		
		size_query.query.group_by = ["aspect_ratio"]

		try:
			size = size_query[aspect_ratio_id]
			
			# get the largest size with this aspect ratio
			return Size.objects.all().filter(size_set=size_set, aspect_ratio=size.aspect_ratio, auto_size=0).order_by("-width")[0]
		except IndexError:
			return None

class Size(CachingMixin, models.Model):
	
	objects = SizeManager()
	
	name = models.CharField(max_length=255, db_index=True)
	
	slug = models.SlugField(max_length=50, null=False,)
	
	height = models.PositiveIntegerField(blank=True, null=True)
	
	width = models.PositiveIntegerField(blank=True, null=True)
	
	auto_size = models.PositiveIntegerField("Thumbnail Generation", default=0, choices=GENERATION_CHOICES)

	size_set = models.ForeignKey(SizeSet)
	
	aspect_ratio = models.FloatField(default=1)
	
	create_on_request = models.BooleanField("Crop on request", default=False)
	
	retina = models.BooleanField("Auto-create retina thumb", default=False,)
	
	def clean(self):
		if not (self.width or self.height):
			raise ValidationError("Size requires either a width, a height, or both")
			
		elif GENERATION_CHOICES[self.auto_size][1] == "Auto-Crop" and not (self.width and self.height):
			# Raise a validation error if one of the sizes is not set for cropping.
			# Auto-size is the only one that can take a missing size.
			raise ValidationError("Auto-crop requires both sizes be specified")
	
	def save(self, *args, **kwargs):
		self.aspect_ratio = utils.aspect_ratio(self.width, self.height)
		super(Size, self).save(*args, **kwargs)
	
	class Meta:
		db_table = "cropduster_size"
	
	def __unicode__(self):
		return u"%s: %sx%s" % (self.name, self.width, self.height)

	
	@property
	def retina_size(self):
		retina_size = copy.copy(self)
		retina_size.width = retina_size.width * 2
		retina_size.height = retina_size.height * 2
		retina_size.slug = u"%s%s" % (retina_size.slug, RETINA_POSTFIX)

		return retina_size

class Crop(CachingMixin, models.Model):
	class Meta:
		db_table = "cropduster_crop"
		unique_together = (("size", "image"),)
		
	objects = CachingManager()
		
	crop_x = models.PositiveIntegerField(default=0, blank=True, null=True)
	crop_y = models.PositiveIntegerField(default=0, blank=True, null=True)
	crop_w = models.PositiveIntegerField(default=0, blank=True, null=True)
	crop_h = models.PositiveIntegerField(default=0, blank=True, null=True)
	
	size = models.ForeignKey(
		"cropduster.Size", 
		related_name = "size",
		verbose_name = "sizes",
	)
	image = models.ForeignKey(
		"cropduster.Image", 
		related_name = "images",
		verbose_name = "images",
	)
	
	def __unicode__(self):
		return u"%s: %sx%s" % (self.image.image, self.size.width, self.size.height)


	def save(self, *args, **kwargs):
		super(Crop, self).save(*args, **kwargs)

		if self.size:
			# get all the manually cropped sizes with the same aspect ratio as this crop/size
			sizes = Size.objects.all().filter(
				aspect_ratio=self.size.aspect_ratio, 
				size_set=self.size.size_set,
				auto_size=0,
			).order_by("-width")
			
			if sizes:
				# create the cropped image 
				cropped_image = utils.create_cropped_image(
					self.image.path, 
					self.crop_x, 
					self.crop_y, 
					self.crop_w, 
					self.crop_h
				)
				
				# loop through the other sizes of the same aspect ratio, and create those crops
				for size in sizes:
					self.image.rescale(cropped_image, size=size)


class Image(CachingMixin, models.Model):
	
	objects = CachingManager()
	
	image = models.ImageField(
		upload_to=settings.CROPDUSTER_UPLOAD_PATH + "%Y/%m/%d", 
		max_length=255, 
		db_index=True
	)
	
	size_set = models.ForeignKey(
		SizeSet,
	)
	
	attribution = models.CharField(max_length=255, blank=True, null=True)
	
	caption = models.CharField(max_length=255, blank=True, null=True)
	
	class Meta:
		db_table = "cropduster_image"
		verbose_name = "Image"
		verbose_name_plural = "Image"
		
	def __unicode__(self):
		if self.image:
			return u"%s" % self.image.url
		else:
			return ""

	@property
	def extension(self):
		if hasattr(self.image, "url"):
			file_root, extension = os.path.splitext(self.image.path)
			return extension
		else:
			return ""
	@property
	def path(self):
		return self.image.path
		
	@property
	def folder_path(self):
		file_path, file = os.path.split(self.image.path)
		file_root, extension = os.path.splitext(file)
		return u"%s" % os.path.join(file_path, file_root)
		
	def thumbnail_path(self, size_slug, retina=False):
		format = u"%s%s"
		if retina:
			format = u"%s" + RETINA_POSTFIX + "%s"

		return format % (os.path.join(self.folder_path, size_slug), self.extension)

	def retina_thumbnail_path(self, size_slug):
		return self.thumbnail_path(size_slug, retina=True)
		
	@property
	def folder_url(self):
		if hasattr(self.image, "url"):
			file_path, file = os.path.split(self.image.url)
			file_root, extension = os.path.splitext(file)
			return u"%s" % os.path.join(file_path, file_root)
		else:
			return ""
		
	def thumbnail_url(self, size_slug, retina=False):
		format = u"%s%s"
		if retina:
			format = u"%s" + RETINA_POSTFIX + "%s"
		return format % (os.path.join(self.folder_url, size_slug), self.extension)

		
	def retina_thumbnail_url(self, size_slug):
		return self.thumbnail_url(size_slug, retina=True)
		
			
	def has_size(self, size_slug):
		return self.size_set.size_set.filter(slug=size_slug).exists()
			
	def get_absolute_url(self):
		return settings.STATIC_URL + self.image
		

	def get_crop(self, size):
		"""  Gets the crop for this image and size based on size set and aspect ratio """		
		return Crop.objects.get(size__size_set=size.size_set, size__aspect_ratio=size.aspect_ratio, image=self)


	def save(self, *args, **kwargs):

		super(Image, self).save(*args, **kwargs)
		
		# get all the auto sized thumbnails and create them
		sizes = self.size_set.size_set.all().filter(
			auto_size__in=[1,2], 
			create_on_request=False
		)
		for size in sizes:
			self.create_thumbnail(size)
			
	def clean(self):
	
		if self.image:
		
			if os.path.splitext(self.image.name)[1] == '':
				raise ValidationError("Please make sure images have file extensions before uploading")
		
			try:
				pil_image = pil.open(self.image)
			except:
				raise ValidationError("Unable to open image file")
				
			for size in self.size_set.size_set.all():
				if size.width > pil_image.size[0] or size.height > pil_image.size[1]:
					raise ValidationError("Uploaded image (%s x %s) is smaller than a required thumbnail size: %s" % (pil_image.size[0], pil_image.size[1], size))
		return super(Image, self).clean()
			
	def create_thumbnail(self, size, force_crop=False):
		""" Creates a thumbnail for an image at the specified size """
	
		if not size.auto_size:
			try:
				crop = self.get_crop(size)
				
				cropped_image = utils.create_cropped_image(
					self.image.path, 
					crop.crop_x, 
					crop.crop_y, 
					crop.crop_w, 
					crop.crop_h
				)
			except Crop.DoesNotExist:
				# auto-crop if no crop is defined
				cropped_image = pil.open(self.image.path)
		else:
			cropped_image = pil.open(self.image.path)
		
		self.rescale(cropped_image=cropped_image, size=size, force_crop=force_crop)


			
	def rescale(self, cropped_image, size, force_crop=False):
		""" Resizes and saves the image to other sizes of the same aspect ratio from a given cropped image"""
		if force_crop or not size.create_on_request:
			auto_crop = (size.auto_size == AUTO_CROP)
			thumbnail = utils.rescale(cropped_image, size.width, size.height, auto_crop=auto_crop)
		
			if not os.path.exists(self.folder_path):
				os.makedirs(self.folder_path)
			
			thumbnail.save(self.thumbnail_path(size.slug), **IMAGE_SAVE_PARAMS)
			
			# Create retina image
			if size.retina:
				retina_size = size.retina_size
				
				# Only create retina image if cropped image is large enough
				# If retina size is required, make a separate size
				if not retina_size.greater_than_image_size(cropped_image.size[0], cropped_image.size[1]):
					retina_thumbnail = utils.rescale(cropped_image, retina_size.width, retina_size.height, crop=retina_size.auto_size)
					retina_thumbnail.save(self.thumbnail_path(retina_size.slug), **IMAGE_SAVE_PARAMS)
			





class CropDusterField(models.ForeignKey):
	pass	


try:
	from south.modelsinspector import add_introspection_rules
except ImportError:
	pass
else:
	add_introspection_rules([], ["^cropduster\.models\.CropDusterField"])
