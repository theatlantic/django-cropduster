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

import os
import copy
import shutil

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
from django.utils.encoding import force_text
from django.utils.functional import cached_property
from django.utils import six
from django.utils.six.moves import filter, map, zip
from django.views.decorators.csrf import csrf_exempt

import PIL.Image

from generic_plus.utils import get_relative_media_url

from cropduster.files import ImageFile
from cropduster.models import Thumb, Size, StandaloneImage, Image
from cropduster.settings import (
    CROPDUSTER_PREVIEW_WIDTH as PREVIEW_WIDTH,
    CROPDUSTER_PREVIEW_HEIGHT as PREVIEW_HEIGHT)
from cropduster.utils import (
    json, is_animated_gif, has_animated_gif_support, process_image)
from cropduster.exceptions import json_error, CropDusterResizeException, full_exc_info

from .base import View
from .forms import CropForm, ThumbForm, ThumbFormSet, UploadForm
from .utils import get_admin_base_template, FakeQuerySet


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
        preview_width, preview_height = PREVIEW_WIDTH, PREVIEW_HEIGHT
        preview_size = self.request.GET.get('preview_size', '').split('x')
        if len(preview_size) != 2:
            preview_size = (PREVIEW_WIDTH, PREVIEW_HEIGHT)
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
        ordered_thumbs = [thumb_dict.get(s.name, Thumb(name=s.name)) for s in self.sizes]
        return FakeQuerySet(ordered_thumbs, thumbs)

    @cached_property
    def orig_image(self):
        if self.db_image:
            return self.db_image.image
        else:
            return self.image_file.get_for_size('original')

    def get(self, *args, **kwargs):
        orig_image = self.orig_image
        if orig_image:
            orig_w = getattr(orig_image, 'width', None) or 0
            orig_h = getattr(orig_image, 'height', None) or 0
            orig_image_name = getattr(orig_image, 'name', None)
        else:
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
            'image': getattr(self.image_file.preview_image, 'url', u"%scropduster/img/blank.gif" % settings.STATIC_URL),
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
def upload(request):
    if request.method == 'GET':
        return index(request)

    # The data we'll be returning as JSON
    data = {
        'warning': [],
    }

    form = UploadForm(request.POST, request.FILES)

    if not form.is_valid():
        errors = form['image'].errors or form.errors
        return json_error(request, 'upload', action="uploading file",
                errors=[force_text(errors)])

    form_data = form.cleaned_data
    is_standalone = bool(form_data.get('standalone'))

    orig_file_path = form_data['image'].name
    if six.PY2 and isinstance(orig_file_path, unicode):
        orig_file_path = orig_file_path.encode('utf-8')
    orig_image = get_relative_media_url(orig_file_path)
    img = PIL.Image.open(orig_file_path)
    (w, h) = (orig_w, orig_h) = img.size

    if is_animated_gif(img) and not has_animated_gif_support():
        data['warning'].append(
            u"This server does not have animated gif support; your uploaded image "
            u"has been made static.")

    tmp_image = Image(image=orig_image)
    preview_w = form_data.get('preview_width') or PREVIEW_WIDTH
    preview_h = form_data.get('preview_height') or PREVIEW_HEIGHT

    # First pass resize if it's too large
    resize_ratio = min(preview_w / w, preview_h / h)

    def fit_preview(im):
        (w, h) = im.size
        if resize_ratio < 1:
            w = int(round(w * resize_ratio))
            h = int(round(h * resize_ratio))
            preview_img = im.resize((w, h), PIL.Image.ANTIALIAS)
        else:
            preview_img = im
        return preview_img

    if not is_standalone:
        preview_file_path = tmp_image.get_image_path('_preview')
        process_image(img, preview_file_path, fit_preview)

    data.update({
        'crop': {
            'orig_image': orig_image,
            'orig_w': orig_w,
            'orig_h': orig_h,
            'image_id': None,
        },
        'url': tmp_image.get_image_url('_preview'),
        'orig_image': orig_image,
        'orig_w': orig_w,
        'orig_h': orig_h,
        'width': w,
        'height': h,
    })
    if not is_standalone:
        return HttpResponse(json.dumps(data), content_type='application/json')

    size = Size('crop', w=img.size[0], h=img.size[1])

    md5 = form_data.get('md5')
    try:
        standalone_image = StandaloneImage.objects.get(md5=md5)
    except StandaloneImage.DoesNotExist:
        standalone_image = StandaloneImage(md5=md5, image=orig_image)
        standalone_image.save()
    cropduster_image, created = Image.objects.get_or_create(
        content_type=ContentType.objects.get_for_model(StandaloneImage),
        object_id=standalone_image.pk)

    if not cropduster_image.image:
        cropduster_image.image = orig_image
        cropduster_image.save()
    elif cropduster_image.image.name != orig_image:
        data['crop']['orig_image'] = data['orig_image'] = cropduster_image.image.name
        data['url'] = cropduster_image.get_image_url('_preview')

    img = PIL.Image.open(cropduster_image.image.path)
    preview_file_path = cropduster_image.get_image_path('_preview')
    if not os.path.exists(preview_file_path):
        process_image(img, preview_file_path, fit_preview)

    thumb = cropduster_image.save_size(size, standalone=True)

    sizes = form_data.get('sizes') or []
    if len(sizes) == 1:
        size = sizes[0]
    else:
        size = Size('crop')

    data.update({
        'thumbs': [{
            'crop_x': thumb.crop_x,
            'crop_y': thumb.crop_y,
            'crop_w': thumb.crop_w,
            'crop_h': thumb.crop_h,
            'width':  thumb.width,
            'height': thumb.height,
            'id': None,
            'changed': True,
            'size': json.dumps(size),
            'name': thumb.name,
        }]
    })
    data['crop'].update({
        'image_id': cropduster_image.pk,
        'sizes': json.dumps([size]),
    })
    return HttpResponse(json.dumps(data), content_type='application/json')


@csrf_exempt
@login_required
def crop(request):
    if request.method == "GET":
        return json_error(request, 'crop', action="cropping image",
                errors=["Form submission invalid"])

    crop_form = CropForm(request.POST, request.FILES, prefix='crop')
    if not crop_form.is_valid():
        return json_error(request, 'crop', action='submitting form', forms=[crop_form],
                log=True, exc_info=full_exc_info())

    crop_data = copy.deepcopy(crop_form.cleaned_data)
    db_image = Image(image=crop_data['orig_image'])
    try:
        pil_image = PIL.Image.open(db_image.image.path)
    except IOError:
        pil_image = None

    FormSet = modelformset_factory(Thumb, form=ThumbForm, formset=ThumbFormSet)
    thumb_formset = FormSet(request.POST, request.FILES, prefix='thumbs')

    if not thumb_formset.is_valid():
        return json_error(request, 'crop', action='submitting form', formsets=[thumb_formset],
                log=True, exc_info=full_exc_info())

    cropped_thumbs = thumb_formset.save(commit=False)

    non_model_fields = set(ThumbForm.declared_fields) - set([f.name for f in Thumb._meta.fields])

    # The fields we will pull from when populating the ThumbForm initial data
    json_thumb_fields = ['id', 'name', 'width', 'height']

    thumbs_with_crops = [t for t in cropped_thumbs if t.crop_w and t.crop_h]
    thumbs_data = [f.cleaned_data for f in thumb_formset]

    standalone_mode = crop_data['standalone']

    for i, (thumb, thumb_form) in enumerate(zip(cropped_thumbs, thumb_formset)):
        changed_fields = set(thumb_form.changed_data) - non_model_fields
        thumb_form._changed_data = list(changed_fields)
        thumb_data = thumbs_data[i]
        size = thumb_data['size']

        if changed_fields & set(['crop_x', 'crop_y', 'crop_w', 'crop_h']):
            # Clear existing primary key to force new thumb creation
            thumb.pk = None

            thumb.width = min(filter(None, [thumb.width, thumb.crop_w]))
            thumb.height = min(filter(None, [thumb.height, thumb.crop_h]))

            try:
                new_thumbs = db_image.save_size(size, thumb, tmp=True, standalone=standalone_mode)
            except CropDusterResizeException as e:
                return json_error(request, 'crop',
                                  action="saving size", errors=[force_text(e)])

            if not new_thumbs:
                continue

            if standalone_mode:
                thumb = new_thumbs
                new_thumbs = {thumb.name: thumb}

            cropped_thumbs[i] = thumb = new_thumbs.get(thumb.name, thumb)

            update_props = ['crop_x', 'crop_y', 'crop_w', 'crop_h', 'width', 'height', 'id', 'name']
            for prop in update_props:
                thumbs_data[i][prop] = getattr(thumb, prop)

            thumbs_data[i].update({
                'changed': True,
                'url': db_image.get_image_url(thumb.name),
            })

            for name, new_thumb in six.iteritems(new_thumbs):
                thumb_data = dict([(k, getattr(new_thumb, k)) for k in json_thumb_fields])
                crop_data['thumbs'].update({name: thumb_data})
                if new_thumb.reference_thumb_id:
                    continue
                thumbs_data[i]['thumbs'].update({name: thumb_data})
        elif thumb.pk and thumb.name and thumb.crop_w and thumb.crop_h:
            thumb_path = db_image.get_image_path(thumb.name, tmp=False)
            tmp_thumb_path = db_image.get_image_path(thumb.name, tmp=True)
            if os.path.exists(thumb_path):
                if not thumb_form.cleaned_data.get('changed') or not os.path.exists(tmp_thumb_path):
                    shutil.copy(thumb_path, tmp_thumb_path)

        if not thumb.pk and not thumb.crop_w and not thumb.crop_h:
            if not len(thumbs_with_crops):
                continue
            best_fit = thumb_form.cleaned_data['size'].fit_to_crop(
                    thumbs_with_crops[0], original_image=pil_image)
            if best_fit:
                thumbs_data[i].update({
                    'crop_x': best_fit.box.x1,
                    'crop_y': best_fit.box.y1,
                    'crop_w': best_fit.box.w,
                    'crop_h': best_fit.box.h,
                    'changed': True,
                    'id': None,
                })

    for thumb_data in thumbs_data:
        if isinstance(thumb_data['id'], Thumb):
            thumb_data['id'] = thumb_data['id'].pk

    return HttpResponse(json.dumps({
        'crop': crop_data,
        'thumbs': thumbs_data,
        'initial': True,
    }), content_type='application/json')
