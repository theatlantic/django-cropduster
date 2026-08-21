from django import forms
from django.core.exceptions import ObjectDoesNotExist
from django.forms.forms import NON_FIELD_ERRORS
from django.forms.models import BaseModelFormSet
from django.forms.utils import ErrorDict as _ErrorDict
from django.utils.encoding import force_str
from django.utils.html import conditional_escape
from django.utils.safestring import mark_safe

from cropduster.exceptions import CropDusterImageException, ImageTooSmallError
from cropduster.files import VirtualFieldFile
from cropduster.models import Thumb
from cropduster.services.upload import store_upload
from cropduster.utils import json


class ErrorDict(_ErrorDict):

    def as_ul(self):
        if not self: return ''
        error_list = []
        for k, v in self.items():
            if k == NON_FIELD_ERRORS:
                k = ''
            error_list.append('%s%s' % (k, conditional_escape(force_str(v))))

        return mark_safe('<ul class="errorlist">%s</ul>'
                % ''.join(['<li>%s</li>' % e for e in error_list]))


def clean_upload_data(data):
    try:
        result = store_upload(
            data['image'],
            upload_to=data.get('upload_to') or None,
            sizes=data.get('sizes'),
            preview_size=(
                data.get('preview_width'), data.get('preview_height')),
            # The 4.x upload view writes its own preview, so none is
            # written here.
            preview=False,
            for_size=data.get('for_size'))
    except (ImageTooSmallError, CropDusterImageException) as error:
        raise forms.ValidationError({'image': [str(error)]})

    data['image'] = VirtualFieldFile(result.original_name)
    data['md5'] = result.md5
    data['upload_result'] = result

    return data


class FormattedErrorMixin(object):

    def full_clean(self):
        super(FormattedErrorMixin, self).full_clean()
        if self._errors:
            self._errors = ErrorDict(self._errors)

    def _clean_form(self):
        try:
            self.cleaned_data = self.clean()
        except forms.ValidationError as e:
            self._errors = e.update_error_dict(self._errors)
            # Wrap newly updated self._errors values in self.error_class
            # (defaults to django.forms.util.ErrorList)
            for k, v in self._errors.items():
                if isinstance(v, list) and not isinstance(v, self.error_class):
                    self._errors[k] = self.error_class(v)
            if not isinstance(self._errors, _ErrorDict):
                self._errors = ErrorDict(self._errors)


class UploadForm(FormattedErrorMixin, forms.Form):

    image = forms.FileField(required=True)
    md5 = forms.CharField(required=False)
    sizes = forms.CharField(required=False)
    image_element_id = forms.CharField(required=False)
    standalone = forms.BooleanField(required=False)
    upload_to = forms.CharField(required=False)

    # The width and height of the image to be generated for
    # crop preview after upload
    preview_width = forms.IntegerField(required=False)
    preview_height = forms.IntegerField(required=False)

    def clean(self):
        data = super(UploadForm, self).clean()
        return clean_upload_data(data)

    def clean_sizes(self):
        sizes = self.cleaned_data.get('sizes')
        try:
            return json.loads(sizes)
        except:
            return []


class CropForm(forms.Form):

    class Media:
        css = {'all': (
            "cropduster/css/cropduster.css",
            "cropduster/css/jquery.jcrop.css",
            "cropduster/css/upload.css",
        )}
        js = (
            "cropduster/js/json2.js",
            "cropduster/js/jquery.class.js",
            "cropduster/js/jquery.form.js",
            "cropduster/js/jquery.jcrop.js",
            "cropduster/js/cropduster.js",
            "cropduster/js/upload.js",
        )

    image_id = forms.IntegerField(required=False)
    orig_image = forms.CharField(max_length=512, required=False)
    orig_w = forms.IntegerField(required=False)
    orig_h = forms.IntegerField(required=False)
    sizes = forms.CharField()
    thumbs = forms.CharField(required=False)
    standalone = forms.BooleanField(required=False)

    def clean_sizes(self):
        try:
            json.loads(self.cleaned_data.get('sizes', '[]'))
        except:
            return []

    def clean_thumbs(self):
        try:
            return json.loads(self.cleaned_data.get('thumbs', '{}'))
        except:
            return {}


class ThumbForm(forms.ModelForm):

    id = forms.IntegerField(required=False, widget=forms.HiddenInput)
    thumbs = forms.CharField(required=False)
    size = forms.CharField(required=False)
    changed = forms.BooleanField(required=False)

    class Meta:
        model = Thumb
        fields = (
            'id', 'name', 'width', 'height',
            'crop_x', 'crop_y', 'crop_w', 'crop_h', 'thumbs', 'size', 'changed')

    def clean_size(self):
        try:
            return json.loads(self.cleaned_data.get('size', 'null'))
        except:
            return None

    def clean_thumbs(self):
        try:
            return json.loads(self.cleaned_data.get('thumbs', '{}'))
        except:
            return {}


class ThumbFormSet(BaseModelFormSet):
    """
    If the form submitted empty strings for thumb pks, change to None before
    calling AutoField.get_prep_value() (so that int('') doesn't throw a
    ValueError).
    """

    def _existing_object(self, pk):
        """
        Avoid potentially expensive list comprehension over self.queryset()
        in the parent method.
        """
        if not hasattr(self, '_object_dict'):
            self._object_dict = {}
        if not pk:
            return None
        try:
            obj = self.get_queryset().get(pk=pk)
        except ObjectDoesNotExist:
            return None
        else:
            self._object_dict[obj.pk] = obj
        return super(ThumbFormSet, self)._existing_object(pk)

    def _construct_form(self, i, **kwargs):
        if self.is_bound and i < self.initial_form_count():
            mutable = getattr(self.data, '_mutable', False)
            self.data._mutable = True
            pk_key = "%s-%s" % (self.add_prefix(i), self.model._meta.pk.name)
            self.data[pk_key] = self.data.get(pk_key) or None
            self.data._mutable = mutable
        form = super(ThumbFormSet, self)._construct_form(i, **kwargs)
        if self.data.get('crop-standalone') == 'on':
            form.fields[self.model._meta.pk.name].required = False
        return form
