from __future__ import division

import os
import hashlib

import PIL.Image

from django import forms
from django.core.exceptions import ObjectDoesNotExist
from django.conf import settings
from django.forms.forms import NON_FIELD_ERRORS
from django.forms.models import BaseModelFormSet
from django.forms.utils import ErrorDict as _ErrorDict
from django.utils.encoding import force_text
from django.utils.html import conditional_escape
from django.utils.safestring import mark_safe
from django.utils import six

from cropduster.models import Thumb
from cropduster.utils import (json, get_upload_foldername, get_min_size,
    get_image_extension)


class ErrorDict(_ErrorDict):

    def as_ul(self):
        if not self: return u''
        error_list = []
        for k, v in self.items():
            if k == NON_FIELD_ERRORS:
                k = ''
            error_list.append(u'%s%s' % (k, conditional_escape(force_text(v))))

        return mark_safe(u'<ul class="errorlist">%s</ul>'
                % ''.join([u'<li>%s</li>' % e for e in error_list]))


def clean_upload_data(data):
    image = data['image']
    image.seek(0)
    try:
        pil_image = PIL.Image.open(image)
    except IOError as e:
        if e.errno:
            error_msg = force_text(e)
        else:
            error_msg = u"Invalid or unsupported image file"
        raise forms.ValidationError({"image": [error_msg]})
    else:
        extension = get_image_extension(pil_image)

    upload_to = data['upload_to'] or None
    folder_path = get_upload_foldername(image.name, upload_to=upload_to)

    (w, h) = (orig_w, orig_h) = pil_image.size
    sizes = data.get('sizes')
    if sizes:
        (min_w, min_h) = get_min_size(sizes)

        if (orig_w < min_w or orig_h < min_h):
            raise forms.ValidationError({"image": [(
                u"Image must be at least %(min_w)sx%(min_h)s "
                u"(%(min_w)s pixels wide and %(min_h)s pixels high). "
                u"The image you uploaded was %(orig_w)sx%(orig_h)s pixels.") % {
                    "min_w": min_w,
                    "min_h": min_h,
                    "orig_w": orig_w,
                    "orig_h": orig_h
                }]})

    if w <= 0:
        raise forms.ValidationError({"image": [u"Invalid image: width is %d" % w]})
    elif h <= 0:
        raise forms.ValidationError({"image": [u"Invalid image: height is %d" % h]})

    # File is good, get rid of the tmp file
    orig_file_path = os.path.join(folder_path, 'original' + extension)
    image.seek(0)
    image_contents = image.read()
    with open(os.path.join(settings.MEDIA_ROOT, orig_file_path), 'wb+') as f:
        f.write(image_contents)
    md5_hash = hashlib.md5()
    md5_hash.update(image_contents)
    data['md5'] = md5_hash.hexdigest()
    data['image'] = open(os.path.join(settings.MEDIA_ROOT, orig_file_path), mode='rb')
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
            for k, v in six.iteritems(self._errors):
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
            u"%scropduster/css/cropduster.css?v=5" % settings.STATIC_URL,
            u"%scropduster/css/jquery.jcrop.css?v=4" % settings.STATIC_URL,
            u"%scropduster/css/upload.css?v=6" % settings.STATIC_URL,
        )}
        js = (
            u"%scropduster/js/json2.js" % settings.STATIC_URL,
            u"%scropduster/js/jquery.class.js" % settings.STATIC_URL,
            u"%scropduster/js/jquery.form.js?v=1" % settings.STATIC_URL,
            u"%scropduster/js/jquery.jcrop.js?v=5" % settings.STATIC_URL,
            u"%scropduster/js/cropduster.js?v=8" % settings.STATIC_URL,
            u"%scropduster/js/upload.js?v=16" % settings.STATIC_URL,
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
        return super(ThumbFormSet, self)._construct_form(i, **kwargs)
