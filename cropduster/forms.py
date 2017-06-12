import django
from django import forms
from django.core.exceptions import ValidationError
from django.forms.models import ModelChoiceIterator
from django.forms.models import ChoiceField, ModelMultipleChoiceField
from django.utils.html import escape, conditional_escape
from django.utils import six

try:
    # Django 1.8+
    from django.forms.utils import flatatt
except ImportError:
    from django.forms.util import flatatt

try:
    from django.utils.encoding import force_text
except ImportError:
    from django.utils.encoding import force_unicode as force_text

from generic_plus.forms import BaseGenericFileInlineFormSet, GenericForeignFileWidget

from .utils import json


__all__ = ('CropDusterWidget', 'CropDusterThumbFormField', 'CropDusterInlineFormSet')


class CropDusterWidget(GenericForeignFileWidget):

    sizes = None

    template = "cropduster/custom_field.html"

    class Media:
        css = {'all': ('cropduster/css/cropduster.css',)}
        js = (
            'cropduster/js/jsrender.js',
            'cropduster/js/cropduster.js',
        )

    def get_context_data(self, name, value, attrs=None, bound_field=None):
        ctx = super(CropDusterWidget, self).get_context_data(name, value, attrs, bound_field)
        sizes = self.sizes
        if six.callable(sizes):
            instance = getattr(getattr(bound_field, 'form', None), 'instance', None)
            related_object = ctx['instance']
            sizes_callable = getattr(sizes, 'im_func', sizes)
            sizes = sizes_callable(instance, related=related_object)
        ctx.update({
            'sizes': json.dumps(sizes),
        })
        return ctx


class ThumbChoiceIterator(ModelChoiceIterator):

    def __iter__(self):
        if self.field.empty_label is not None:
            yield ("", self.field.empty_label)
        if getattr(self.field, 'cache_choices', None):
            if self.field.choice_cache is None:
                self.field.choice_cache = [
                    self.choice(obj) for obj in self.queryset
                ]
            for choice in self.field.choice_cache:
                yield choice
        else:
            for obj in self.queryset:
                yield self.choice(obj)

    def choice(self, obj):
        return (obj, self.field.label_from_instance(obj))


class CropDusterThumbWidget(forms.SelectMultiple):

    def __init__(self, *args, **kwargs):
        from cropduster.models import Thumb

        super(CropDusterThumbWidget, self).__init__(*args, **kwargs)
        self.model = Thumb

    def render_option(self, selected_choices, option_value, option_label):
        attrs = {}
        if isinstance(option_value, self.model):
            thumb = option_value
            option_value = thumb.pk
        else:
            try:
                thumb = self.model.objects.get(pk=option_value)
            except (TypeError, self.model.DoesNotExist):
                thumb = None

        if thumb:
            # If the thumb has no images associated with it then
            # it has not yet been saved, and so its file path has
            # '_tmp' appended before the extension.
            use_tmp_file = not(thumb.image_id)
            attrs = {
                'data-width': thumb.width,
                'data-height': thumb.height,
                'data-tmp-file': json.dumps(use_tmp_file),
            }
        option_value = force_text(option_value)
        if option_value in selected_choices:
            selected_html = u' selected="selected"'
            if not self.allow_multiple_selected:
                # Only allow for a single selection.
                selected_choices.remove(option_value)
        else:
            selected_html = ''
        return (
            u'<option value="%(value)s"%(selected)s%(attrs)s>%(label)s</option>') % {
                'value': escape(option_value),
                'selected': selected_html,
                'attrs': flatatt(attrs),
                'label': conditional_escape(force_text(option_label)),
        }


class CropDusterThumbFormField(ModelMultipleChoiceField):

    widget = CropDusterThumbWidget

    def clean(self, value):
        """
        Override default validation so that it doesn't throw a ValidationError
        if a given value is not in the original queryset.
        """
        try:
            value = super(CropDusterThumbFormField, self).clean(value)
        except ValidationError as e:
            if self.error_messages['required'] in e.messages:
                raise
            elif self.error_messages['list'] in e.messages:
                raise
        return value

    def _get_choices(self):
        if hasattr(self, '_choices'):
            return self._choices
        return ThumbChoiceIterator(self)

    choices = property(_get_choices, ChoiceField._set_choices)


def get_cropduster_field_on_model(model, field_identifier):
    from cropduster.fields import CropDusterField

    opts = model._meta
    if hasattr(opts, 'get_fields'):
        # Django 1.8+
        m2m_fields = [f for f in opts.get_fields() if f.many_to_many and not f.auto_created]
    else:
        m2m_fields = opts.many_to_many

    if hasattr(opts, 'private_fields'):
        # Django 1.10+
        private_fields = opts.private_fields
    else:
        # Django < 1.10
        private_fields = opts.virtual_fields

    m2m_related_fields = set(m2m_fields + private_fields)

    field_match = lambda f: (isinstance(f, CropDusterField)
        and f.field_identifier == field_identifier)

    try:
        return [f for f in m2m_related_fields if field_match(f)][0]
    except IndexError:
        return None


class CropDusterInlineFormSet(BaseGenericFileInlineFormSet):

    fields = ('image', 'thumbs', 'attribution', 'attribution_link',
        'caption', 'alt_text', 'field_identifier')

    def __init__(self, *args, **kwargs):
        super(CropDusterInlineFormSet, self).__init__(*args, **kwargs)
        if self.instance and not self.data:
            cropduster_field = get_cropduster_field_on_model(self.instance.__class__, self.field_identifier)
            if cropduster_field:
                # An order_by() is required to prevent the queryset result cache
                # from being removed
                self.queryset = self.queryset.order_by('pk')
                field_file = getattr(self.instance, cropduster_field.name)
                self.queryset._result_cache = list(filter(None, [field_file.related_object]))

    def _construct_form(self, i, **kwargs):
        """
        Limit the queryset of the thumbs for performance reasons (so that it doesn't
        pull in every available thumbnail into the selectbox)
        """
        from cropduster.models import Thumb

        form = super(CropDusterInlineFormSet, self)._construct_form(i, **kwargs)

        field_identifier_field = form.fields['field_identifier']
        field_identifier_field.widget = forms.HiddenInput()
        field_identifier_field.initial = self.field_identifier

        thumbs_field = form.fields['thumbs']

        if form.instance and form.instance.pk:
            # Set the queryset to the current list of thumbs on the image
            if django.VERSION < (1, 6):
                thumbs_field.queryset = form.instance.thumbs.get_query_set()
            else:
                thumbs_field.queryset = form.instance.thumbs.get_queryset()
        else:
            # Start with an empty queryset
            thumbs_field.queryset = Thumb.objects.none()

        if form.data:
            # Check if thumbs from POST data should be used instead.
            # These can differ from the values in the database if a
            # ValidationError elsewhere prevented saving.
            try:
                thumb_pks = [int(v) for v in form['thumbs'].value()]
            except (TypeError, ValueError):
                pass
            else:
                if thumb_pks and thumb_pks != [o.pk for o in thumbs_field.queryset]:
                    thumbs_field.queryset = Thumb.objects.filter(pk__in=thumb_pks)

        return form
