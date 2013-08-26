from __future__ import division

import os
import copy
import shutil

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.forms.models import modelformset_factory
from django.http import HttpResponse, HttpResponseNotAllowed
from django.shortcuts import render_to_response
from django.template import RequestContext
from django.views.decorators.csrf import csrf_exempt

import PIL.Image

from cropduster.models import Thumb, Size, StandaloneImage, Image as CropDusterImage
from cropduster.settings import CROPDUSTER_PREVIEW_WIDTH, CROPDUSTER_PREVIEW_HEIGHT
from cropduster.utils import json, get_relative_media_url
from cropduster.exceptions import json_error, CropDusterResizeException, full_exc_info

from .forms import CropForm, ThumbForm, ThumbFormSet, UploadForm, StandaloneUploadForm
from .utils import get_admin_base_template, FakeQuerySet
from .standalone import standalone


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
        tmp_image = CropDusterImage(image=request.GET['image'])
        if os.path.exists(tmp_image.get_image_path('_preview')):
            try:
                img = PIL.Image.open(tmp_image.get_image_path())
            except:
                pass
            else:
                orig_image = tmp_image.get_image_name()
                if orig_image != initial.get('orig_image'):
                    del initial['image_id']
                initial.update({
                    'orig_image': orig_image,
                    'orig_w': img.size[0],
                    'orig_h': img.size[1],
                })
                ctx['image'] = tmp_image.get_image_url('_preview')

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

    # This error checking might be too aggressive...
    preview_size = request.GET.get('preview_size', '').split('x')
    if len(preview_size) != 2:
        preview_size = (CROPDUSTER_PREVIEW_WIDTH, CROPDUSTER_PREVIEW_HEIGHT)
    try:
        preview_width = int(preview_size[0])
    except (ValueError, TypeError):
        preview_width = CROPDUSTER_PREVIEW_WIDTH
        preview_height = CROPDUSTER_PREVIEW_HEIGHT
    else:
        try:
            preview_height = int(preview_size[1])
        except (ValueError, TypeError):
            preview_width = CROPDUSTER_PREVIEW_WIDTH
            preview_height = CROPDUSTER_PREVIEW_HEIGHT

    ctx.update({
        'is_popup': True,
        'orig_image': '',
        'parent_template': get_admin_base_template(),
        'upload_form': UploadForm(initial={
            'upload_to': request.GET.get('upload_to', ''),
            'sizes': initial['sizes'],
            'image_element_id': request.GET.get('el_id', ''),
            'preview_width': preview_width,
            'preview_height': preview_height,
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

    if request.GET.get('standalone') == '1':
        form = StandaloneUploadForm(request.POST, request.FILES)
    else:
        form = UploadForm(request.POST, request.FILES)

    if not form.is_valid():
        errors = form['image'].errors or form.errors
        return json_error(request, 'upload', action="uploading file",
                errors=[unicode(errors)])

    form_data = form.cleaned_data

    orig_file_path = form_data['image'].name
    orig_image = get_relative_media_url(orig_file_path)
    img = PIL.Image.open(orig_file_path)
    (w, h) = (orig_w, orig_h) = img.size

    tmp_image = CropDusterImage(image=orig_image)

    preview_w = form_data.get('preview_width') or CROPDUSTER_PREVIEW_WIDTH
    preview_h = form_data.get('preview_height') or CROPDUSTER_PREVIEW_HEIGHT

    # First pass resize if it's too large
    resize_ratio = min(preview_w / w, preview_h / h)
    if resize_ratio < 1:
        w = int(round(w * resize_ratio))
        h = int(round(h * resize_ratio))
        preview_img = img.resize((w, h), PIL.Image.ANTIALIAS)
    else:
        preview_img = img

    preview_file_path = tmp_image.get_image_path('_preview')

    img_save_params = {}
    if preview_img.format == 'JPEG':
        img_save_params['quality'] = 95

    preview_img.save(preview_file_path, **img_save_params)

    data = {
        'crop': {
            'orig_image': orig_image,
            'orig_w': orig_w,
            'orig_h': orig_h,
        },
        'url': tmp_image.get_image_url('_preview'),
        'orig_image': orig_image,
        'orig_w': orig_w,
        'orig_h': orig_h,
        'width': w,
        'height': h,
    }
    if not form_data.get('standalone'):
        return HttpResponse(json.dumps(data), mimetype='application/json')

    size = Size('crop', w=img.size[0], h=img.size[1])

    md5 = form_data.get('md5')
    try:
        standalone_image = StandaloneImage.objects.get(md5=md5)
    except StandaloneImage.DoesNotExist:
        standalone_image = StandaloneImage(md5=md5, image=orig_image)
        standalone_image.save()
    cropduster_image, created = CropDusterImage.objects.get_or_create(
        content_type=ContentType.objects.get_for_model(StandaloneImage),
        object_id=standalone_image.pk)

    if not cropduster_image.image:
        cropduster_image.image = orig_image
    thumb = cropduster_image.save_size(size, standalone=True)
    thumb_path = cropduster_image.get_image_path(thumb.name)

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

    standalone_mode = crop_data['standalone']

    for i, (thumb, thumb_form) in enumerate(zip(cropped_thumbs, thumb_formset)):
        changed_fields = set(thumb_form.changed_data) - non_model_fields
        thumb_form._changed_data = list(changed_fields)
        thumb_data = thumbs_data[i]
        size = thumb_data['size']

        if changed_fields & set(['crop_x', 'crop_y', 'crop_w', 'crop_h']):
            thumb.pk = None

            if standalone_mode:
                thumb.width = min(filter(None, [thumb.width, thumb.crop_w]))
                thumb.height = min(filter(None, [thumb.height, thumb.crop_h]))

            try:
                new_thumbs = db_image.save_size(size, thumb, tmp=True, standalone=standalone_mode)
            except CropDusterResizeException as e:
                return json_error(request, 'crop',
                                  action="saving size", errors=[unicode(e)])

            if not new_thumbs:
                continue

            if standalone_mode:
                thumb = new_thumbs
                new_thumbs = {thumb.name: thumb}

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
                'name': thumb.name,
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
