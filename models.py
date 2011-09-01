from django.db import models
from django.conf import settings
import os
from django.contrib.contenttypes.generic import GenericRelation
from decimal import Decimal
from cropduster import utils


IMAGE_SAVE_PARAMS =  {'quality' :95}

class SizeSet(models.Model):
	name = models.CharField(max_length=255, db_index=True)
	
	slug = models.SlugField(max_length=50, null=False,)
	
	def __unicode__(self):
		return u"%s" % self.name
		
	def get_size_by_ratio(self):
		size_query = self.size_set.all()
		size_query.query.group_by = ["aspect_ratio"]
		try:
			return size_query
		except ValueError:
			return None

class SizeManager(models.Manager):
	def get_size_by_ratio(self, size_set, aspect_ratio_id):
		size_query = Size.objects.all().filter(size_set=size_set).exclude(auto_size=1).order_by("-aspect_ratio")
		size_query.query.group_by = ["aspect_ratio"]

		try:
			return size_query[aspect_ratio_id]
		except:
			return None

class Size(models.Model):
	
	name = models.CharField(max_length=255, db_index=True)
	
	slug = models.SlugField(max_length=50, null=False,)
	
	height = models.PositiveIntegerField(default=0, blank=True, null=True)
	
	width = models.PositiveIntegerField(default=0, blank=True, null=True)
	
	auto_size = models.BooleanField(default=False)
	
	size_set = models.ForeignKey(SizeSet)
	
	aspect_ratio = models.FloatField(default=1)
	
	objects = SizeManager()
	
	def save(self, *args, **kwargs):
		self.aspect_ratio = Decimal(str(round(float(self.width)/float(self.height), 2)))
		super(Size, self).save(*args, **kwargs)
	
	class Meta:
		db_table = 'cropduster_size'
	
	def __unicode__(self):
		return u"%s: %sx%s" % (self.name, self.width, self.height)

class Crop(models.Model):
	class Meta:
		db_table = 'cropduster_crop'
		
	crop_x = models.PositiveIntegerField(default=0, blank=True, null=True)
	crop_y = models.PositiveIntegerField(default=0, blank=True, null=True)
	crop_w = models.PositiveIntegerField(default=0, blank=True, null=True)
	crop_h = models.PositiveIntegerField(default=0, blank=True, null=True)
	
	size = models.ForeignKey(
		'cropduster.Size', 
		related_name = 'size',
		verbose_name = 'sizes',
	)
	image = models.ForeignKey(
		'cropduster.Image', 
		related_name = 'images',
		verbose_name = 'images',
	)
	
	def __unicode__(self):
		return u"%s: %sx%s" % (self.image.image, self.size.width, self.size.height)


	def save(self, *args, **kwargs):
		super(Crop, self).save(*args, **kwargs)

		if self.size:
			sizes = Size.objects.all().filter(aspect_ratio=self.size.aspect_ratio).order_by("-width")
			if sizes:
				cropped_image = utils.create_cropped_image(self.image.image.path, self.crop_x, self.crop_y, self.crop_w, self.crop_h)
					
				for size in sizes:
					
					thumbnail = utils.rescale(cropped_image, size.width, size.height, crop=size.auto_size)
	
					if not os.path.exists(self.image.folder_path):
						os.makedirs(self.image.folder_path)
					
					thumbnail.save(self.image.thumbnail_path(size), **IMAGE_SAVE_PARAMS)


class Image(models.Model):
	
	image = models.ImageField(
		upload_to=settings.CROPDUSTER_UPLOAD_PATH + '%Y/%m/%d', 
		max_length=255, 
		db_index=True
		)
	size_set = models.ForeignKey(
		SizeSet,
	)
	attribution = models.CharField(max_length=255, blank=True, null=True)

	class Meta:
		db_table = 'cropduster_image'
		verbose_name = 'Image'

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
		
	def thumbnail_url(self, size):
		file_path, file = os.path.split(self.image.url)
		file_root, extension = os.path.splitext(file)
		return u"%s" % os.path.join(file_path, file_root, size.slug) + extension

	def __unicode__(self):
		return u'%s' % self.image.url

	def get_absolute_url(self):
		return settings.STATIC_URL + self.image
	

class CropDusterField(models.ForeignKey):
	pass	


