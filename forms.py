import os
import re

from django.conf import settings

from django import forms
from django.db.models.fields import related
from django.forms.models import ModelMultipleChoiceField
from django.forms.widgets import Input
from django.contrib.contenttypes.generic import BaseGenericInlineFormSet, generic_inlineformset_factory
from django.core.exceptions import ValidationError
from django.core.urlresolvers import reverse
from django.template.loader import render_to_string

from cropduster.models import Image, Thumb
from cropduster.utils import get_aspect_ratios, validate_sizes, OrderedDict, get_min_size

from jsonutil import jsonutil

class CropDusterWidget(Input):
	
	def __init__(self, sizes=None, auto_sizes=None, default_thumb=None, attrs=None):
		self.sizes = sizes
		self.auto_sizes = auto_sizes
		self.default_thumb = default_thumb
		self.formset = generic_inlineformset_factory(Image)

		if attrs is not None:
			self.attrs = attrs.copy()
		else:
			self.attrs = {}
	
	def get_media(self):
		"""
		A method used to dynamically generate the media property,
		since we may not have the urls ready at the time of import,
		and then the reverse() call would fail.
		"""
		from django.forms.widgets import Media as _Media
		media_url = reverse('cropduster-static', kwargs={'path':''})
		media_cls = type('Media', (_Media,), {
			'css': {
				'all': (os.path.join(media_url, 'css/CropDuster.css?v=1'), )
			},
			'js': (os.path.join(media_url, 'js/CropDuster.js'), )
		})
		return _Media(media_cls)
	
	media = property(get_media)
	
	def render(self, name, value, attrs=None):
		from jsonutil import jsonutil as json
		import simplejson
		
		final_attrs = self.build_attrs(attrs, type=self.input_type, name=name)
	
		self.value = value
		thumbs = OrderedDict({})

		if value is None or value == "":
			has_value = False
			final_attrs['value'] = ""
			display_value = ""

		else:
			has_value = True		
			final_attrs['value'] = value
			image = Image.objects.get(pk=value)
			for thumb in image.thumbs.order_by('-width').all():
				size_name = thumb.name
				thumbs[size_name] = image.get_image_url(size_name)
		
		final_attrs['sizes'] = simplejson.dumps(self.sizes)
		final_attrs['auto_sizes'] = simplejson.dumps(self.auto_sizes)
	
		if self.default_thumb is not None:
			default_thumb = self.default_thumb
		else:
			default_thumb = ''
	
		aspect_ratios = get_aspect_ratios(self.sizes)
		aspect_ratio = json.dumps(aspect_ratios[0])
		min_size = json.dumps(get_min_size(self.sizes, self.auto_sizes))
		formset = self.formset
		inline_admin_formset = self.formset
		prefix = getattr(self.formset, 'prefix', self.formset.get_default_prefix())
		static_url = simplejson.dumps(settings.STATIC_URL)
		return render_to_string("cropduster/custom_field.html", locals())


class CropDusterFormField(forms.IntegerField):
	
	def __init__(self, sizes=None, auto_sizes=None, default_thumb=None, *args, **kwargs):
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
		
		widget = CropDusterWidget(sizes=sizes, auto_sizes=auto_sizes, default_thumb=default_thumb)
		kwargs['widget'] = widget
		super(CropDusterFormField, self).__init__(*args, **kwargs)
	
	def _sizes_validate(self, sizes, is_auto=False):
		validate_sizes(sizes)	
		if not is_auto:
			aspect_ratios = get_aspect_ratios(sizes)
			if len(aspect_ratios) > 1:
				raise ValueError("More than one aspect ratio: %s" % jsonutil.dumps(aspect_ratios))

class CropDusterThumbField(ModelMultipleChoiceField):
	def clean(self, value):
		"""
		Override default validation so that it doesn't throw a ValidationError
		if a given value is not in the original queryset.
		"""
		required_msg = self.error_messages['required']
		list_msg = self.error_messages['list']
		ret = value
		try:
			ret = super(CropDusterThumbField, self).clean(value)
		except ValidationError, e:
			if required_msg in e.messages or list_msg in e.messages:
				raise e
		return ret

class CropDusterForm(forms.ModelForm):
	model = Image
	
	@staticmethod
	def formfield_for_dbfield(db_field, **kwargs):
		if isinstance(db_field, related.ManyToManyField) and db_field.column == 'thumbs':
			return db_field.formfield(form_class=CropDusterThumbField)
		else:
			return db_field.formfield()

class AbstractInlineFormSet(BaseGenericInlineFormSet):
	model = Image
	fields = ('id', 'crop_x', 'crop_y', 'crop_w', 'crop_h',
	           'path', '_extension', 'default_thumb', 'thumbs',)
	extra_fields = None
	exclude = None
	sizes = None
	auto_sizes = None
	default_thumb = None
	exclude = ["content_type", "object_id"]
	max_num = 1
	can_order = False
	can_delete = True
	extra = 1
	label = "Upload"
	
	def __init__(self, *args, **kwargs):
		label = kwargs.pop('label', None)
		if label is not None:
			self.label = label
		sizes = kwargs.pop('sizes', None)
		if sizes is not None:
			self.sizes = sizes
		default_sizes = kwargs.pop('default_sizes', None)
		if default_sizes is not None:
			self.default_sizes = default_sizes
		default_thumb = kwargs.pop('default_thumb', None)
		if default_thumb is not None:
			self.default_thumb = default_thumb
		extra = kwargs.pop('extra', None)
		if extra is not None:
			self.extra = extra
		
		extra_fields = kwargs.pop('extra_fields', None)
		if extra_fields is not None:
			self.extra_fields = extra_fields
		if hasattr(self.extra_fields, 'iter'):
			for field in self.extra_fields:
				self.fields.append(field)
		
		super(AbstractInlineFormSet, self).__init__(*args, **kwargs)
	
	def _construct_form(self, i, **kwargs):
		"""
		Override the id field of the form with our CropDusterFormField and
		override the thumbs queryset for performance.
		"""
		
		image_id = 0
		try:
			image_id = self.queryset[0].id
		except:
			pass
		
		# Limit the queryset for performance reasons
		queryset = None
		try:
			queryset = Image.objects.get(pk=image_id).thumbs.get_query_set()
			self.form.base_fields['thumbs'].queryset = queryset
		except Image.DoesNotExist:
			if self.data is not None and len(self.data) > 0:
				thumb_ids = [int(id) for id in self.data.getlist(self.rel_name + '-0-thumbs')]
				queryset = Thumb.objects.filter(pk__in=thumb_ids)
			else:
				# Return an empty queryset
				queryset = Thumb.objects.filter(pk=0)

		if queryset is not None:
			self.form.base_fields['thumbs'].queryset = queryset
			widget = self.form.base_fields['thumbs'].widget
			try:
				if hasattr(self.form.base_fields['thumbs'].widget, 'widget'):
					self.form.base_fields['thumbs'].widget.widget.choices.queryset = queryset
				else:
					self.form.base_fields['thumbs'].widget.choices.queryset = queryset
			except AttributeError:
				pass
			
		
		if self.data is not None and len(self.data) > 0:
			pk_key = "%s-%s" % (self.add_prefix(i), self.model._meta.pk.name)
			pk = self.data[pk_key]
			if pk == '' and image_id != 0:
				self.data[pk_key] = image_id

			if self.data.get(self.rel_name + '-0-id') == '':
				img_kwargs = {}
				for field_name in self.form.base_fields:
					if field_name not in ('DELETE', 'id', 'thumbs'):
						img_kwargs[field_name] = self.data.get('%s-%s' % (self.add_prefix(i), field_name))
						if field_name in ('crop_x', 'crop_y', 'crop_w', 'crop_h'):
							img_kwargs[field_name] = int(img_kwargs[field_name])
				try:
					if image_id != 0:
						img = Image.objects.get(pk=image_id)
						# If cache machine exists, invalidate
					else:
						img = Image(**img_kwargs)
					self.form.instance = img
					try:
						Image.objects.invalidate(img)
					except:
						pass
					try:
						# Invalidate parent instance
						self.instance.__class__.objects.invalidate(self.instance)
					except:
						pass
				except Exception, e:
					pass

		form = super(AbstractInlineFormSet, self)._construct_form(i, **kwargs)
		
		# Override the id field to use our custom field and widget that displays the
		# thumbnail and the button that pops up the cropduster window
		form.fields['id'] = CropDusterFormField(
			label = self.label,
			sizes = self.sizes,
			auto_sizes = self.auto_sizes,
			default_thumb=self.default_thumb,
			required=False
		)
		
		# Load in initial data if we have it from a previously submitted
		# (but apparently invalidated) form
		if self.data is not None and len(self.data) > 0:
			thumb_ids = [int(id) for id in self.data.getlist(self.rel_name + '-0-thumbs')]
			if len(thumb_ids) > 0:
				for key in self.data.keys():
					if key.find(self.rel_name) == 0:
						match = re.match(self.rel_name + '-(.+)$', key)
						if match:
							field_name = match.group(1)
							if field_name in form.fields:
								field = form.fields[field_name]
								field.initial = self.data.get(key)
		return form


def cropduster_formset_factory():
	ct_field = Image._meta.get_field("content_type")
	ct_fk_field = Image._meta.get_field("object_id")
	
	exclude = [ct_field.name, ct_fk_field.name]
	
	form = type('CropDusterForm', (CropDusterForm,), {
		"model": Image,
		"formfield_overrides": {
			Thumb: {
				'form_class': CropDusterThumbField,
			},
		},
		"formfield_callback": CropDusterForm.formfield_for_dbfield,
		"Meta": type('Meta', (object,), {
			"formfield_callback": CropDusterForm.formfield_for_dbfield,
			"fields": AbstractInlineFormSet.fields,
			"exclude": exclude,
			"model": Image,
		})
	})
	
	
	return type('BaseInlineFormSet', (AbstractInlineFormSet, ), {
		"formfield_callback": CropDusterForm.formfield_for_dbfield,
		"ct_field": ct_field,
		"ct_fk_field": ct_fk_field,
		"exclude": exclude,
		"form": form,
	})

BaseInlineFormSet = cropduster_formset_factory()