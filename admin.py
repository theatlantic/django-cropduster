from django.contrib.contenttypes.generic import GenericInlineModelAdmin
from cropduster.models import Image, Thumb
from cropduster.forms import BaseInlineFormset, CropDusterFormField, CropDusterThumbField


class BaseImageInline(GenericInlineModelAdmin):
	# These need to be overridden in the calling admin.py
	sizes = None
	auto_sizes = None
	default_thumb = None
		
	model = Image
	template = "cropduster/inline.html"
	formset = BaseInlineFormset
	extra = 1
	max_num = 1
	readonly_fields = 'id'
	
	fieldsets = (
		('Image', {
			'fields': ('id', 'crop_x', 'crop_y', 'crop_w', 'crop_h',
			           'path', '_extension', 'default_thumb', 'thumbs',),
		}),
	)

	# This can be overridden in the calling admin.py to hide non-essential fields
	extra_fields = ('attribution', )

	def __init__(self, *args, **kwargs):
		try:
			fields = list(self.fieldsets[0][1]['fields'])
			for field in self.extra_fields:
				fields.append(field)
			self.fieldsets[0][1]['fields'] = tuple(fields)
		except:
			pass

		super(BaseImageInline, self).__init__(*args, **kwargs)

	def formfield_for_manytomany(self, db_field, request=None, **kwargs):
		"""
        Override default ManyToManyField form field for thumbs.
        """
		if db_field.column == 'thumbs':
			kwargs['form_class'] = CropDusterThumbField
		
		return super(BaseImageInline, self).formfield_for_manytomany(db_field, request, **kwargs)

	def get_formset(self, request, obj=None):
		formset = super(BaseImageInline, self).get_formset(request, obj)
		formset.sizes = self.sizes
		formset.auto_sizes = self.auto_sizes
		formset.default_thumb = self.default_thumb
		return formset


# Retained for backwards compatibility, but imports of these classes from this module
# are deprecated
from cropduster.forms import BaseInlineFormset
from cropduster.forms import CropDusterFormField as _CropDusterFormField
from cropduster.forms import CropDusterThumbField as _CropDusterThumbField

class ImageInlineFormset(BaseInlineFormset):
	def __init__(self, *args, **kwargs):
		import warnings
		warnings.warn(
			'Calls to cropduster.admin.ImageInlineFormset are deprecated. Please use ' +\
			'cropduster.forms.BaseInlineFormset',
			PendingDeprecationWarning
		)
		return super(ImageInlineFormset, self).__init__(*args, **kwargs)

class CropDusterFormField(_CropDusterFormField):
	def __init__(self, *args, **kwargs):
		import warnings
		warnings.warn(
			'Calls to cropduster.admin.CropDusterFormField are deprecated. Please use ' +\
			'cropduster.forms.CropDusterFormField',
			PendingDeprecationWarning
		)
		return super(CropDusterFormField, self).__init__(*args, **kwargs)

class CropDusterThumbField(_CropDusterThumbField):
	def __init__(self, *args, **kwargs):
		import warnings
		warnings.warn(
			'Calls to cropduster.admin.CropDusterThumbField are deprecated. Please use ' +\
			'cropduster.forms.CropDusterThumbField',
			PendingDeprecationWarning
		)
		return super(CropDusterThumbField, self).__init__(*args, **kwargs)
		

