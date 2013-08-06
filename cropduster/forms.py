import re
import json

from jsonutil import jsonutil

from django import forms
from django.conf import settings
from django.core import validators
from django.db import models
from django.db.models.fields.files import ImageFieldFile
from django.forms.models import ModelMultipleChoiceField
from django.forms.widgets import Input
from django.contrib.contenttypes.generic import generic_inlineformset_factory
from django.core.exceptions import ValidationError
from django.template.loader import render_to_string

from .generic import GenericInlineFormSet
from .models import Image, Thumb
from .settings import CROPDUSTER_UPLOAD_PATH
from .utils import get_aspect_ratios, validate_sizes, OrderedDict, get_min_size, relpath


class CropDusterWidget(Input):

    sizes = None
    auto_sizes = None
    default_thumb = None
    field = None

    class Media:
        css = {'all': (u'%scropduster/css/CropDuster.css' % settings.STATIC_URL,),}
        js = (u'%scropduster/js/CropDuster.js' % settings.STATIC_URL,)

    def __init__(self, field=None, sizes=None, auto_sizes=None, default_thumb=None, attrs=None):
        self.field = field
        self.sizes = sizes or self.sizes
        self.auto_sizes = auto_sizes or self.auto_sizes
        self.default_thumb = default_thumb or self.default_thumb
        self.formset = generic_inlineformset_factory(Image)

        if attrs is not None:
            self.attrs = attrs.copy()
        else:
            self.attrs = {}
    
    def render(self, name, value, attrs=None):
        final_attrs = self.build_attrs(attrs, type=self.input_type, name=name)

        # Whether we are rendering from the generated inline formset
        # or rendering on the actual form.
        is_formset_render = bool('content_type-object_id' in name)

        image = None
        image_value = ''
        if isinstance(value, models.Manager):
            try:
                value = value.all()[0]
            except IndexError:
                value = None
            else:
                value = value.pk
        elif isinstance(value, Image):
            image = value
            value = value.pk
        elif isinstance(value, ImageFieldFile):
            image = value.cropduster_image
            image_value = value.name
            value = getattr(image, 'pk', None)
        elif isinstance(value, basestring) and not value.isdigit():
            try:
                image = Image.objects.get_by_relpath(value)
            except Image.DoesNotExist:
                image = None
                image_value = value
                value = None
            else:
                image_value = value
                value = image.pk

        self.value = value
        thumbs = OrderedDict({})

        if value is None or value == "":
            final_attrs['value'] = ""
        else:
            final_attrs['value'] = value
            if image is None:
                image = Image.objects.get(pk=value)
            for thumb in image.thumbs.filter(name=self.default_thumb).order_by('-width'):
                size_name = thumb.name
                thumbs[size_name] = image.get_image_url(size_name)

        final_attrs['sizes'] = jsonutil.dumps(self.sizes)
        final_attrs['auto_sizes'] = jsonutil.dumps(self.auto_sizes)

        relative_path = relpath(settings.MEDIA_ROOT, CROPDUSTER_UPLOAD_PATH)
        if re.match(r'\.\.', relative_path):
            raise Exception("Upload path is outside of static root")

        return render_to_string("cropduster/custom_field.html", {
            'image_value': image_value,
            'is_formset_render': is_formset_render,
            'formset': self.formset,
            'inline_admin_formset': self.formset,
            'prefix': getattr(self.formset, 'prefix', self.formset.get_default_prefix()),
            'static_url': json.dumps(u'%s/%s/' % (settings.MEDIA_URL, relative_path)),
            'min_size': jsonutil.dumps(get_min_size(self.sizes, self.auto_sizes)),
            'aspect_ratio': jsonutil.dumps(get_aspect_ratios(self.sizes)[0]),
            'default_thumb': self.default_thumb or '',
            'final_attrs': final_attrs,
            'thumbs': thumbs
        })


class CropDusterFormField(forms.Field):

    sizes = None
    auto_sizes = None
    default_thumb = None

    def __init__(self, sizes=None, auto_sizes=None, default_thumb=None, *args, **kwargs):
        if not sizes and self.sizes:
            sizes = self.sizes
        if not auto_sizes and self.auto_sizes:
            auto_sizes = self.auto_sizes
        if not default_thumb and self.default_thumb:
            default_thumb = self.default_thumb

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
        
        widget = CropDusterWidget(field=self, sizes=sizes, auto_sizes=auto_sizes, default_thumb=default_thumb)
        kwargs['widget'] = widget
        super(CropDusterFormField, self).__init__(*args, **kwargs)

    def _sizes_validate(self, sizes, is_auto=False):
        validate_sizes(sizes)    
        if not is_auto:
            aspect_ratios = get_aspect_ratios(sizes)
            if len(aspect_ratios) > 1:
                raise ValueError("More than one aspect ratio: %s" % jsonutil.dumps(aspect_ratios))

    def to_python(self, value):
        value = super(CropDusterFormField, self).to_python(value)
        if value in validators.EMPTY_VALUES:
            return None

        if isinstance(value, basestring) and not value.isdigit():
            return value

        try:
            value = int(str(value))
        except (ValueError, TypeError):
            raise ValidationError(self.error_messages['invalid'])
        return value


def cropduster_formfield_factory(sizes, auto_sizes, default_thumb):
    return type('CropDusterFormField',
        (CropDusterFormField,), {
            'sizes': sizes,
            'auto_sizes': auto_sizes,
            'default_thumb': default_thumb})


def cropduster_widget_factory(sizes, auto_sizes, default_thumb):
    return type('CropDusterWidget', (CropDusterWidget,), {
        'sizes': sizes,
        'auto_sizes': auto_sizes,
        'default_thumb': default_thumb,})


class CropDusterThumbField(ModelMultipleChoiceField):

    def clean(self, value):
        """
        Override default validation so that it doesn't throw a ValidationError
        if a given value is not in the original queryset.
        """
        try:
            value = super(CropDusterThumbField, self).clean(value)
        except ValidationError, e:
            if self.error_messages['required'] in e.messages:
                raise
            elif self.error_messages['list'] in e.messages:
                raise
        return value


class CropDusterForm(forms.ModelForm):

    model = Image

    @staticmethod
    def formfield_for_dbfield(db_field, **kwargs):
        if isinstance(db_field, models.ManyToManyField) and db_field.column == 'thumbs':
            return db_field.formfield(form_class=CropDusterThumbField)
        else:
            return db_field.formfield()


class AbstractInlineFormSet(GenericInlineFormSet):

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
        self.label = kwargs.pop('label', None) or self.label
        self.sizes = kwargs.pop('sizes', None) or self.sizes
        self.default_thumb = kwargs.pop('default_thumb', None) or self.default_thumb
        self.extra = kwargs.pop('extra', None) or self.extra        
        self.extra_fields = kwargs.pop('extra_fields', None) or self.extra_fields
        if hasattr(self.extra_fields, 'iter'):
            for field in self.extra_fields:
                self.fields.append(field)
        
        super(AbstractInlineFormSet, self).__init__(*args, **kwargs)
    
    def _pre_construct_form(self, i, **kwargs):
        """
        Limit the queryset of the thumbs for performance reasons (so that it doesn't
        pull in every available thumbnail into the selectbox)
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
            thumb_field = self.form.base_fields['thumbs']
            thumb_field.queryset = queryset
            try:
                if hasattr(thumb_field.widget, 'widget'):
                    thumb_field.widget.widget.choices.queryset = queryset
                else:
                    thumb_field.widget.choices.queryset = queryset
            except AttributeError:
                pass

    def _post_construct_form(self, form, i, **kwargs):
        """
        Override the id field of the form with our CropDusterFormField and
        override the thumbs queryset for performance.
        """
        # Override the id field to use our custom field and widget that displays the
        # thumbnail and the button that pops up the cropduster window
        form.fields['id'] = CropDusterFormField(
            label = self.label,
            sizes = self.sizes,
            auto_sizes = self.auto_sizes,
            default_thumb=self.default_thumb,
            required=False
        )
        return form


def cropduster_formset_factory(sizes=None, auto_sizes=None, model=Image, **kwargs):
    ct_field = model._meta.get_field("content_type")
    ct_fk_field = model._meta.get_field("object_id")
    exclude = [ct_field.name, ct_fk_field.name]
    formfield_callback = kwargs.get('formfield_callback') or CropDusterForm.formfield_for_dbfield

    form = type('CropDusterForm', (CropDusterForm,), {
        "model": model,
        "formfield_overrides": {
            Thumb: {'form_class': CropDusterThumbField,},
        },
        "formfield_callback": formfield_callback,
        "Meta": type('Meta', (object,), {
            "formfield_callback": formfield_callback,
            "fields": AbstractInlineFormSet.fields,
            "exclude": exclude,
            "model": model,
        }),
        '__module__': CropDusterForm.__module__,
    })

    inline_formset_attrs = {
        "formfield_callback": formfield_callback,
        "ct_field": ct_field,
        "ct_fk_field": ct_fk_field,
        "exclude": exclude,
        "form": form,
        "model": model,
        '__module__': AbstractInlineFormSet.__module__,
    }
    if sizes is not None:
        inline_formset_attrs['sizes'] = sizes
    if auto_sizes is not None:
        inline_formset_attrs['auto_sizes'] = auto_sizes
    if kwargs.get('default_thumb') is not None:
        inline_formset_attrs['default_thumb'] = kwargs['default_thumb']

    return type('BaseInlineFormSet', (AbstractInlineFormSet, ), inline_formset_attrs)
