from django.db import models
from django.conf import settings
import os
from cropduster import utils
from PIL import Image as pil
from south.modelsinspector import add_introspection_rules
from django.core.exceptions import ValidationError


CROPDUSTER_UPLOAD_PATH = getattr(settings, 'CROPDUSTER_UPLOAD_PATH', "")

IMAGE_SAVE_PARAMS =  {"quality" :95}

GENERATION_CHOICES = (
	(0, "Manually Crop"),
	(1, "Auto-Crop"),
	(2, "Auto-Size"),
)

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


class SizeManager(CachingManager):
	def get_size_by_ratio(self, size_set, aspect_ratio_id):
	
		size_query = Size.objects.all().only("aspect_ratio").filter(size_set=size_set, auto_size=0).order_by("-aspect_ratio")
		
		size_query.query.group_by = ["aspect_ratio"]

		try:
			size = size_query[aspect_ratio_id]
			
			# get the largest size with this aspect ratio
			return Size.objects.all().filter(size_set=size_set, aspect_ratio=size.aspect_ratio, auto_size=0).order_by("-width")[0]
		except:
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
	
	def clean(self):
		if not (self.width or self.height):
			raise ValidationError("Crop size requires either a width, a height, or both")
		elif GENERATION_CHOICES[self.auto_size][1] != "Auto-Size" and not (self.width and self.height):
			"""
			Raise a validation error if one of the sizes is not set for cropping.
			Auto-size is the only one that can take a missing size.
			"""
			raise ValidationError("Cropping requires both sizes be valid")
	
	def save(self, *args, **kwargs):
		self.aspect_ratio = utils.aspect_ratio(self.width, self.height)
		super(Size, self).save(*args, **kwargs)
	
	class Meta:
		db_table = "cropduster_size"
	
	def __unicode__(self):
		return u"%s: %sx%s" % (self.name, self.width, self.height)

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
			# get all the sizes with the same aspect ratio as this crop/size
			sizes = Size.objects.all().filter(
				aspect_ratio=self.size.aspect_ratio, 
				size_set=self.size.size_set,
			).filter(auto_size=0).order_by("-width")
			
			if sizes:
				# create the cropped image 
				cropped_image = utils.create_cropped_image(self.image.image.path, self.crop_x, self.crop_y, self.crop_w, self.crop_h)
				
				# loop through the other sizes of the same aspect ratio, and create those crops
				for size in sizes:
					
					thumbnail = utils.rescale(cropped_image, size.width, size.height, crop=size.auto_size)
	
					if not os.path.exists(self.image.folder_path):
						os.makedirs(self.image.folder_path)
					
					thumbnail.save(self.image.thumbnail_path(size), **IMAGE_SAVE_PARAMS)


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

	def save(self, *args, **kwargs):

		super(Image, self).save(*args, **kwargs)

		for size in self.size_set.size_set.all().exclude(auto_size=0):
			auto_crop = True if size.auto_size == 1 else False

			if self.image.width > size.width and self.image.height > size.height:
				thumbnail = utils.rescale(pil.open(self.image.path), size.width, size.height, crop=auto_crop)
			else:
				thumbnail = pil.open(self.image.path)

			if not os.path.exists(self.folder_path):
				os.makedirs(self.folder_path)
			thumbnail.save(self.thumbnail_path(size), **IMAGE_SAVE_PARAMS)

			

	class Meta:
		db_table = "cropduster_image"
		verbose_name = "Image"
		verbose_name_plural = "Image"

	@property
	def extension(self):
		file_root, extension = os.path.splitext(self.image.path)
		return extension
		
	@property
	def folder_path(self):
		file_path, file = os.path.split(self.image.path)
		file_root, extension = os.path.splitext(file)
		return u"%s" % os.path.join(file_path, file_root)
		
	def thumbnail_path(self, size):
		file_path, file = os.path.split(self.image.path)
		file_root, extension = os.path.splitext(file)
		return u"%s" % os.path.join(file_path, file_root, size.slug) + extension
		
	@property
	def folder_url(self):
		file_path, file = os.path.split(self.image.url)
		file_root, extension = os.path.splitext(file)
		return u"%s" % os.path.join(file_path, file_root)
		
	def thumbnail_url(self, size_slug):
		file_path, file = os.path.split(self.image.url)
		file_root, extension = os.path.splitext(file)
		return u"%s" % os.path.join(file_path, file_root, size_slug) + extension
		
	def has_size(self, size_slug):
		try:
			size = self.size_set.size_set.get(slug=size_slug)
			return True
		except Size.DoesNotExist:
			return False

	def __unicode__(self):
		if self.image:
			return u"%s" % self.image.url
		else:
			return ""
			
	def get_absolute_url(self):
		return settings.STATIC_URL + self.image
	

class CropDusterField(models.ForeignKey):
	pass	


try:
	from south.modelsinspector import add_introspection_rules
except ImportError:
	pass
else:
	add_introspection_rules([], ["^cropduster\.models\.CropDusterField"])
