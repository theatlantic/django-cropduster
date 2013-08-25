from __future__ import division

from django import forms
from django.conf import settings
from django.forms.models import BaseModelFormSet

from cropduster.models import Thumb
from cropduster.utils import json


class UploadForm(forms.Form):

    picture = forms.ImageField(required=True)
    sizes = forms.CharField(required=False)
    thumbs = forms.CharField(required=False)

    def clean_sizes(self):
        sizes = self.cleaned_data.get('sizes')
        try:
            return json.loads(sizes)
        except:
            return []

    def clean_thumbs(self):
        thumbs = self.cleaned_data.get('thumbs')
        try:
            return json.loads(thumbs)
        except:
            return {}


class CropForm(forms.Form):

    class Media:
        css = {'all': (
            u"%scropduster/css/cropduster.css?v=3" % settings.STATIC_URL,
            u"%scropduster/css/jquery.jcrop.css?v=3" % settings.STATIC_URL,
            u"%scropduster/css/upload.css?v=3" % settings.STATIC_URL,
        )}
        js = (
            u"%scropduster/js/json2.js" % settings.STATIC_URL,
            u"%scropduster/js/jquery.class.js" % settings.STATIC_URL,
            u"%scropduster/js/jquery.form.js?v=1" % settings.STATIC_URL,
            u"%scropduster/js/jquery.jcrop.js?v=4" % settings.STATIC_URL,
            u"%scropduster/js/upload.js?v=4" % settings.STATIC_URL,
            u"%scropduster/js/cropduster.js?v=3" % settings.STATIC_URL,
        )

    image_id = forms.IntegerField(required=False)
    orig_image = forms.CharField(max_length=512, required=False)
    orig_w = forms.IntegerField(required=False)
    orig_h = forms.IntegerField(required=False)
    sizes = forms.CharField()
    thumbs = forms.CharField(required=False)
    thumb_name = forms.CharField(required=False)

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

    def _construct_form(self, i, **kwargs):
        if self.is_bound and i < self.initial_form_count():
            mutable = getattr(self.data, '_mutable', False)
            self.data._mutable = True
            pk_key = "%s-%s" % (self.add_prefix(i), self.model._meta.pk.name)
            self.data[pk_key] = self.data.get(pk_key) or None
            self.data._multable = mutable
        return super(ThumbFormSet, self)._construct_form(i, **kwargs)
