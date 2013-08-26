from __future__ import division

import os
import re
import copy
import shutil

from django.conf import settings
from django.db.models import Q
from django.forms.models import modelformset_factory
from django.http import HttpResponse, HttpResponseNotAllowed
from django.shortcuts import render_to_response
from django.template import RequestContext
from django.views.decorators.csrf import csrf_exempt

import PIL.Image

from cropduster.models import Thumb, Image as CropDusterImage
from cropduster.utils import (
    json, get_relative_media_url, get_upload_foldername,
    get_image_extension, get_media_url, get_min_size)
from cropduster.exceptions import json_error, CropDusterResizeException, full_exc_info

from .forms import CropForm, ThumbForm, ThumbFormSet, UploadForm
from .utils import get_admin_base_template, FakeQuerySet


def index(request):
    if request.method == "POST":
        raise HttpResponseNotAllowed(['GET'])

    ctx = {}

    initial = {
        'sizes': request.GET.get('sizes', '[]')
    }

    thumb_ids = filter(None, request.GET.get('thumbs', '').split(','))
    try:
        thumb_ids = map(int, thumb_ids)
    except TypeError:
        thumbs = Thumb.objects.none()
    else:
        thumbs = Thumb.objects.filter(pk__in=thumb_ids)
        initial['thumbs'] = json.dumps(dict([
            (t['name'], t)
            for t in thumbs.values('id', 'name', 'width', 'height')]))

    try:
        image = CropDusterImage.objects.get(pk=request.GET.get('id'))
    except (ValueError, CropDusterImage.DoesNotExist):
        pass
    else:
        orig_w, orig_h = image.get_image_size()
        image_path = os.path.split(image.image.name)[0]
        initial.update({
            'image_id': image.pk,
            'orig_image': u'/'.join([image_path, 'original' + image.extension]),
            'orig_w': orig_w,
            'orig_h': orig_h,
        })
        ctx['image'] = image.get_image_url('_preview')

    # If we have a new image that hasn't been saved yet
    if request.GET.get('image'):
        image_path, basename = os.path.split(request.GET['image'])
        root_path = os.path.join(settings.MEDIA_ROOT, image_path)
        ext = os.path.splitext(basename)[1]
        if os.path.exists(os.path.join(root_path, '_preview%s' % ext)):
            preview_url = u'/'.join([settings.MEDIA_URL, image_path, '_preview%s' % ext])
            preview_url = re.sub(r'(?<!:)/+', '/', preview_url) # Remove double '/'
            orig_image = u"%s/original%s" % (image_path, ext)
            try:
                img = PIL.Image.open(os.path.join(settings.MEDIA_ROOT, orig_image))
            except:
                pass
            else:
                if orig_image != initial.get('orig_image'):
                    del initial['image_id']
                initial.update({
                    'orig_image': orig_image,
                    'orig_w': img.size[0],
                    'orig_h': img.size[1],
                })
                ctx['image'] = preview_url

    sizes = json.loads(initial['sizes'])
    size_dict = dict([(s.name, s) for s in sizes])
    thumb_dict = dict([(t.name, t) for t in thumbs])

    # Create a fake queryset with the same order as the image `sizes`.
    # This is necessary if we want the formset thumb order to be consistent.
    ordered_thumbs = [thumb_dict.get(s.name, Thumb(name=s.name)) for s in sizes]
    fake_queryset = FakeQuerySet(ordered_thumbs, thumbs)

    FormSet = modelformset_factory(Thumb, form=ThumbForm, formset=ThumbFormSet, extra=0)
    thumb_formset = FormSet(queryset=fake_queryset, initial=[], prefix='thumbs')

    for thumb_form in thumb_formset.initial_forms:
        name = thumb_form.initial['name']
        if name in size_dict:
            thumb_form.initial['size'] = json.dumps(size_dict[name])
        # The thumb being cropped and thumbs referencing it
        pk = thumb_form.initial['id']
        thumb_group = thumbs.filter(Q(pk=pk) | Q(reference_thumb_id__exact=pk))
        thumb_group_data = dict([(t['name'], t) for t in thumb_group.values('id', 'name', 'width', 'height')])
        thumb_form.initial.update({
            'thumbs': json.dumps(thumb_group_data),
            'changed': False,
        })

    ctx.update({
        'is_popup': True,
        'image_element_id': request.GET.get('el_id', ''),
        'orig_image': '',
        'upload_to': request.GET.get('upload_to', ''),
        'parent_template': get_admin_base_template(),
        'upload_form': UploadForm(initial={
            'sizes': initial['sizes'],
        }),
        'crop_form': CropForm(initial=initial, prefix='crop'),
        'thumb_formset': thumb_formset,
        'image': ctx.pop('image', u"%scropduster/img/blank.gif" % settings.STATIC_URL),
    })
    return render_to_response('cropduster/upload.html', RequestContext(request, ctx))


@csrf_exempt
def upload(request):
    if request.method == 'GET':
        return index(request)

    form = UploadForm(request.POST, request.FILES)

    if not form.is_valid():
        return json_error(request, 'upload', action="uploading file",
                errors=[unicode(form['picture'].errors)])

    img_file = request.FILES['picture']
    extension = os.path.splitext(img_file.name)[1].lower()
    folder_path = get_upload_foldername(img_file.name,
            upload_to=request.GET.get('upload_to', None))

    tmp_file_path = os.path.join(folder_path, '__tmp' + extension)

    with open(tmp_file_path, 'wb+') as f:
        for chunk in img_file.chunks():
            f.write(chunk)
    img = PIL.Image.open(tmp_file_path)

    (w, h) = (orig_w, orig_h) = img.size
    (min_w, min_h) = get_min_size(request.POST['sizes'])

    if (orig_w < min_w or orig_h < min_h):
        return json_error(request, 'upload', action="uploading file", errors=[(
            u"Image must be at least %(min_w)sx%(min_h)s "
            u"(%(min_w)s pixels wide and %(min_h)s pixels high). "
            u"The image you uploaded was %(orig_w)sx%(orig_h)s pixels.") % {
                "min_w": min_w,
                "min_h": min_h,
                "orig_w": orig_w,
                "orig_h": orig_h
            }])

    if w <= 0:
        raise json_error(request, 'upload', action='uploading file', errors=[
            u"Invalid image: width is %d" % w])
    elif h <= 0:
        raise json_error(request, 'upload', action='uploading file', errors=[
            u"Invalid image: height is %d" % h])

    # File is good, get rid of the tmp file
    orig_file_path = os.path.join(folder_path, 'original' + extension)
    os.rename(tmp_file_path, orig_file_path)

    orig_url = get_relative_media_url(orig_file_path)

    # First pass resize if it's too large
    # (height > 500 px or width > 800 px)
    resize_ratio = min(800.0 / w, 500.0 / h)
    if resize_ratio < 1:
        w = int(round(w * resize_ratio))
        h = int(round(h * resize_ratio))
        preview_img = img.resize((w, h), PIL.Image.ANTIALIAS)
    else:
        preview_img = img

    preview_file_path = os.path.join(folder_path, '_preview' + extension)
    img_save_params = {}
    if preview_img.format == 'JPEG':
        img_save_params['quality'] = 95
    try:
        preview_img.save(preview_file_path, **img_save_params)
    except KeyError:
        # The user uploaded an image with an invalid file extension, we need
        # to rename it with the proper one.
        extension = get_image_extension(img)

        os.rename(orig_file_path, os.path.splitext(orig_file_path)[0] + extension)
        orig_file_path = os.path.splitext(orig_file_path)[0] + extension
        orig_url = get_relative_media_url(orig_file_path)

        preview_file_path = os.path.join(folder_path, '_preview' + extension)
        preview_img.save(preview_file_path, **img_save_params)

    data = {
        'crop': {
            'orig_image': orig_url,
            'orig_w': orig_w,
            'orig_h': orig_h,
        },
        'url': get_media_url(preview_file_path),
        'orig_image': get_relative_media_url(orig_url),
        'orig_w': orig_w,
        'orig_h': orig_h,
        'width': w,
        'height': h,
        'orig_url': orig_url,
    }
    return HttpResponse(json.dumps(data), mimetype='application/json')


@csrf_exempt
def crop(request):
    if request.method == "GET":
        return json_error(request, 'crop', action="cropping image",
                errors=["Form submission invalid"])

    crop_form = CropForm(request.POST, request.FILES, prefix='crop')
    if not crop_form.is_valid():
        return json_error(request, 'crop', action='submitting form', forms=[crop_form],
                log=True, exc_info=full_exc_info())

    crop_data = copy.deepcopy(crop_form.cleaned_data)
    db_image = CropDusterImage(image=crop_data['orig_image'])
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

    for i, (thumb, thumb_form) in enumerate(zip(cropped_thumbs, thumb_formset)):
        changed_fields = set(thumb_form.changed_data) - non_model_fields
        thumb_form._changed_data = list(changed_fields)
        if changed_fields & set(['crop_x', 'crop_y', 'crop_w', 'crop_h']):
            thumb.pk = None

            try:
                new_thumbs = db_image.save_size(thumb_form.cleaned_data['size'], thumb, tmp=True)
            except CropDusterResizeException as e:
                return json_error(request, 'crop',
                                  action="saving size", errors=[unicode(e)])

            if not new_thumbs:
                continue
            cropped_thumbs[i] = thumb = new_thumbs.get(thumb.name, thumb)
            thumbs_data[i].update({
                'crop_x': thumb.crop_x,
                'crop_y': thumb.crop_y,
                'crop_w': thumb.crop_w,
                'crop_h': thumb.crop_h,
                'width':  thumb.width,
                'height': thumb.height,
                'id': thumb.id,
                'changed': True,
            })
            for name, new_thumb in new_thumbs.iteritems():
                if new_thumb.reference_thumb_id:
                    continue
                thumb_data = dict([(k, getattr(new_thumb, k)) for k in json_thumb_fields])
                crop_data['thumbs'].update({name: thumb_data})
                thumbs_data[i]['thumbs'].update({name: thumb_data})
        elif thumb.pk and thumb.name and thumb.crop_w and thumb.crop_h:
            thumb_path = db_image.get_image_path(thumb.name, use_temp=False)
            tmp_thumb_path = db_image.get_image_path(thumb.name, use_temp=True)
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
                })

    for thumb_data in thumbs_data:
        if isinstance(thumb_data['id'], Thumb):
            thumb_data['id'] = thumb_data['id'].pk

    return HttpResponse(json.dumps({
        'crop': crop_data,
        'thumbs': thumbs_data,
        'initial': True,
    }), mimetype='application/json')
