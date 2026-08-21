"""
View functions used by the cropduster dialog.

index() (defined in CropDusterIndex)
====================================

The initial page that a user sees when clicking on the "Upload Image" button.
This view renders the form used to interact with upload() and crop() via ajax.


standalone() (defined in CropDusterStandalone)
==============================================

Subclass of CropDusterIndex used for "standalone mode", which saves minimal
information in the database and instead stores information about the original
image and crop dimensions in metadata on the generated image. The intended use
case for standalone mode is a dialog in a WYSIWYG editor.

upload() / crop()
=================

Both upload() and crop() interact with the index page's html in the same way:
they receive a POST with data from the django forms and formsets, create new
image and thumb instances (respectively), and return a JSON object that map
back onto fields on the index page's forms / formsets.
"""
from __future__ import division

import functools
from io import BytesIO
import os
import copy
import shutil
import time

import django
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.forms.models import modelformset_factory
from django.http import HttpResponse
from django.shortcuts import render
from django.template import RequestContext
from django.utils.decorators import method_decorator
from django.utils.encoding import force_str
from django.utils.functional import cached_property
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.generic import View

import PIL.Image

from generic_plus.utils import get_relative_media_url

from cropduster.files import ImageFile
from cropduster.models import Thumb, Size, StandaloneImage, Image
from cropduster.conf import settings as cropduster_settings
from cropduster.resizing import Box
from cropduster.services.crop import ThumbRequest, apply_crops
from cropduster.services.payload import (
    build_payload, legacy_crop_response, payload_to_legacy)
from cropduster.services.upload import adopt_standalone
from cropduster.standalone import NOT_INSTALLED_MESSAGE, standalone_available
from cropduster.utils import (
    json, is_animated_gif, has_animated_gif_support, process_image)
from cropduster.utils.storage import get_image_storage
from cropduster.exceptions import json_error, CropDusterResizeException, full_exc_info

from .forms import CropForm, ThumbForm, ThumbFormSet, UploadForm
from .utils import get_admin_base_template, FakeQuerySet


CROP_FIELDS = frozenset(['crop_x', 'crop_y', 'crop_w', 'crop_h'])


class CropDusterIndex(View):

    http_method_names = ['get']

    is_standalone = False

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        self.request = request
        self.upload_to = self.request.GET.get('upload_to') or None

        return super(CropDusterIndex, self).dispatch(request, *args, **kwargs)

    @cached_property
    def image_file(self):
        (preview_w, preview_h) = self.preview_size
        return ImageFile(self.request.GET.get('image'),
            upload_to=self.upload_to,
            preview_w=preview_w,
            preview_h=preview_h)

    @cached_property
    def preview_size(self):
        # This error checking might be too aggressive...
        default_size = (
            cropduster_settings.CROPDUSTER_PREVIEW_WIDTH,
            cropduster_settings.CROPDUSTER_PREVIEW_HEIGHT)
        preview_width, preview_height = default_size
        preview_size = self.request.GET.get('preview_size', '').split('x')
        if len(preview_size) != 2:
            preview_size = default_size
        try:
            preview_width = int(preview_size[0])
        except (ValueError, TypeError):
            pass
        else:
            try:
                preview_height = int(preview_size[1])
            except (ValueError, TypeError):
                pass
        return (preview_width, preview_height)

    @cached_property
    def db_image(self):
        try:
            db_image = Image.objects.get(pk=self.request.GET.get('id'))
        except (ValueError, Image.DoesNotExist):
            return None

        image_filename = getattr(self.image_file, 'name', None)
        if image_filename and image_filename != db_image.image.name:
            # New images should get new rows (and thus new pks)
            db_image.pk = None
        return db_image

    @cached_property
    def sizes(self):
        return json.loads(self.request.GET.get('sizes', '[]'))

    @cached_property
    def thumbs(self):
        thumb_ids = filter(None, self.request.GET.get('thumbs', '').split(','))
        try:
            thumb_ids = map(int, thumb_ids)
        except TypeError:
            thumbs = Thumb.objects.none()
        else:
            thumbs = Thumb.objects.filter(pk__in=thumb_ids)
        thumb_dict = dict([(t.name, t) for t in thumbs])
        ordered_thumbs = [
            thumb_dict.get(s.name, Thumb(name=s.name)) for s in self.sizes if not s.is_alias]
        return FakeQuerySet(ordered_thumbs, thumbs)

    @cached_property
    def orig_image(self):
        if self.db_image:
            return self.db_image.image
        else:
            return self.image_file.get_for_size('original')

    def get(self, *args, **kwargs):
        orig_image = self.orig_image
        try:
            orig_w = getattr(orig_image, 'width', None) or 0
            orig_h = getattr(orig_image, 'height', None) or 0
            orig_image_name = getattr(orig_image, 'name', None)
        except Exception:
            # If original image not found, allow it to be re-uploaded
            orig_w, orig_h = 0, 0
            orig_image_name = None

        initial = {
            'standalone': self.is_standalone,
            'sizes': json.dumps(self.sizes),
            'thumbs': json.dumps(dict([
                (t['name'], t)
                for t in self.thumbs.queryset.values('id', 'name', 'width', 'height')])),
            'image_id': getattr(self.db_image, 'pk', None) if orig_image else None,
            'orig_image': orig_image_name,
            'orig_w': orig_w,
            'orig_h': orig_h,
        }

        FormSet = modelformset_factory(Thumb, form=ThumbForm, formset=ThumbFormSet, extra=0)
        thumb_formset = FormSet(queryset=self.thumbs, initial=[], prefix='thumbs')

        size_dict = dict([(s.name, s) for s in self.sizes])

        for thumb_form in thumb_formset.initial_forms:
            name = thumb_form.initial['name']
            if name in size_dict:
                thumb_form.initial['size'] = json.dumps(size_dict[name])
            # The thumb being cropped and thumbs referencing it
            pk = thumb_form.initial['id']
            thumb_group = self.thumbs.queryset.filter(Q(pk=pk) | Q(reference_thumb_id__exact=pk))
            thumb_group_data = dict([(t['name'], t) for t in thumb_group.values('id', 'name', 'width', 'height')])
            thumb_form.initial.update({
                'thumbs': json.dumps(thumb_group_data),
                'changed': False,
            })

        return render(self.request, 'cropduster/upload.html', {
            'django_is_gte_19': (django.VERSION[:2] >= (1, 9)),
            'is_popup': True,
            'orig_image': '',
            'parent_template': get_admin_base_template(),
            'image': getattr(self.image_file.preview_image, 'url', "%scropduster/img/blank.gif" % settings.STATIC_URL),
            'standalone': self.is_standalone,
            'upload_form': UploadForm(initial={
                'upload_to': self.upload_to,
                'sizes': initial['sizes'],
                'image_element_id': self.request.GET.get('el_id', ''),
                'standalone': self.is_standalone,
                'preview_width': self.preview_size[0],
                'preview_height': self.preview_size[1],
            }),
            'crop_form': CropForm(initial=initial, prefix='crop'),
            'thumb_formset': thumb_formset,
        })


index = CropDusterIndex.as_view()


@csrf_exempt
@login_required
@xframe_options_exempt
def upload(request):
    if request.method == 'GET':
        return index(request)

    form = UploadForm(request.POST, request.FILES)

    if not form.is_valid():
        errors = form['image'].errors or form.errors
        return json_error(request, 'upload', action="uploading file",
                errors=[force_str(errors)])

    form_data = form.cleaned_data
    is_standalone = bool(form_data.get('standalone'))

    if is_standalone and not standalone_available():
        return json_error(request, 'upload', action="uploading file",
                errors=[NOT_INSTALLED_MESSAGE])

    # Form validation stored the file. Create standalone rows only after the
    # optional metadata dependency has been checked.
    result = form_data['upload_result']
    if is_standalone:
        result = adopt_standalone(
            result, sizes=form_data.get('sizes'),
            preview_size=(
                form_data.get('preview_width'), form_data.get('preview_height')))

    payload = build_payload(
        result.image,
        thumbs=[result.standalone_thumb] if result.standalone_thumb else [],
        sizes=result.sizes,
        preview=result.preview,
        warnings=result.warnings)

    return HttpResponse(
        json.dumps(payload_to_legacy(payload)), content_type='application/json')


@csrf_exempt
@login_required
@xframe_options_exempt
def crop(request):
    if request.method == "GET":
        return json_error(request, 'crop', action="cropping image",
                errors=["Form submission invalid"])

    crop_form = CropForm(request.POST, request.FILES, prefix='crop')
    if not crop_form.is_valid():
        return json_error(request, 'crop', action='submitting form', forms=[crop_form],
                log=True, exc_info=full_exc_info())

    crop_data = copy.deepcopy(crop_form.cleaned_data)
    standalone_mode = crop_data['standalone']

    if standalone_mode and not standalone_available():
        return json_error(request, 'crop', action="cropping image",
                errors=[NOT_INSTALLED_MESSAGE])

    if crop_data.get('image_id'):
        db_image = Image.objects.get(pk=crop_data['image_id'])
    else:
        db_image = Image(image=crop_data['orig_image'])

    try:
        with db_image.image_file_open() as f:
            pil_image = PIL.Image.open(BytesIO(f.read()))
            pil_image.filename = f.name
    except IOError:
        pil_image = None

    FormSet = modelformset_factory(Thumb, form=ThumbForm, formset=ThumbFormSet)
    thumb_formset = FormSet(request.POST, request.FILES, prefix='thumbs')

    if not thumb_formset.is_valid():
        return json_error(request, 'crop', action='submitting form', formsets=[thumb_formset],
                log=True, exc_info=full_exc_info())

    cropped_thumbs = thumb_formset.save(commit=False)

    # Address a standalone mode issue where, because the thumbs don't have a pk value,
    # Django no longer returns them in Formset.save() if they are in initial_forms
    if standalone_mode and not cropped_thumbs and len(thumb_formset.initial_forms):
        thumb_form = thumb_formset.initial_forms[0]
        obj = thumb_form.instance
        cropped_thumbs = [thumb_formset.save_existing(thumb_form, obj, commit=False)]

    thumbs_data = [f.cleaned_data for f in thumb_formset]
    non_model_fields = set(ThumbForm.declared_fields) - set([f.name for f in Thumb._meta.fields])
    thumb_requests = [
        _thumb_request(thumb, thumb_form, thumbs_data[i], non_model_fields)
        for i, (thumb, thumb_form) in enumerate(zip(cropped_thumbs, thumb_formset))]

    try:
        result = apply_crops(
            db_image, thumb_requests, standalone=standalone_mode, tmp=True,
            pil_image=pil_image)
    except CropDusterResizeException as e:
        return json_error(request, 'crop', action="saving size", errors=[force_str(e)])

    return HttpResponse(
        json.dumps(legacy_crop_response(
            db_image.name, crop_data, echo=thumbs_data, result=result)),
        content_type='application/json')


def _thumb_request(thumb, form, data, non_model_fields):
    """Convert one submitted crop form to a service request."""
    changed_fields = set(form.changed_data) - non_model_fields
    return ThumbRequest(
        name=thumb.name,
        size=data['size'],
        thumb_id=thumb.pk,
        # The formset loaded this row while binding the form. Pass it through
        # to avoid another database query in the crop service.
        thumb=thumb,
        crop=_posted_crop_box(thumb),
        width=thumb.width,
        height=thumb.height,
        changed=bool(changed_fields & CROP_FIELDS))


def _posted_crop_box(thumb):
    """Return the submitted crop box, or ``None`` when it is incomplete."""
    box = (thumb.crop_x, thumb.crop_y, thumb.crop_w, thumb.crop_h)
    if any(value is None for value in box):
        return None
    x, y, w, h = box
    return Box(x, y, x + w, y + h)
