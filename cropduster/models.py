import os
import re

from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes import generic
from django.db import models
from django.conf import settings

import PIL.Image

from cropduster.utils import relpath

class Thumb(models.Model):
	name = models.CharField(max_length=255, db_index=True)
	height = models.PositiveIntegerField(default=0, blank=True, null=True)
	width = models.PositiveIntegerField(default=0, blank=True, null=True)

	def __unicode__(self):
		return self.name
	
	class Meta:
		db_table = 'cropduster_thumb'


class Image(models.Model):

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
		db_table = 'cropduster_image'
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

		return os.path.join(settings.CROPDUSTER_UPLOAD_PATH, self.path, size_name + self.extension)

	def has_thumb(self, size_name):
		try:
			thumb = self.thumbs.get(name=size_name)
			return True
		except Thumb.DoesNotExist:
			return False
	
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
		
		relative_path = relpath(settings.STATIC_ROOT, settings.CROPDUSTER_UPLOAD_PATH)
		if re.match(r'\.\.', relative_path):
			raise Exception("Upload path is outside of static root")
		url_root = settings.STATIC_URL + '/' + relative_path + '/'
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


from django.contrib.contenttypes.generic import GenericRelation

class CropDusterField(GenericRelation):
	def db_type(self, connection):
		return ''
		
	def __init__(self, *args, **kwargs):
		kwargs['to'] = Image
		super(CropDusterField, self).__init__(*args, **kwargs)

	def save_form_data(self, instance, data):
		"""
		Override Field.save_form_data to ensure that the
		correct type is saved to the object
		"""
		if data is None or data == '':
			setattr(instance, self.name, data)
		else:
			mgr = getattr(instance, self.name)
			image = Image.objects.get(pk=data)
			mgr.add(image)

try:
	from south.modelsinspector import add_introspection_rules
	add_introspection_rules([], ["^cropduster\.models\.CropDusterField"])
except:
	pass
