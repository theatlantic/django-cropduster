# FROM THE FUTURE LOL
from __future__ import division

import os
import re

try:
    from collections import OrderedDict
except ImportError:
    from django.utils.datastructures import SortedDict as OrderedDict

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.safestring import mark_safe
from django.http import HttpResponse
from django.shortcuts import render_to_response
from django.template import RequestContext
from django.views.decorators.csrf import csrf_exempt

import PIL.Image

from .models import Thumb, Image as CropDusterImage
from .utils import (
    json, rescale, get_relative_media_url, get_upload_foldername,
    get_image_extension, get_media_url, get_min_size)
from .exceptions import json_error, CropDusterViewException, CropDusterResizeException


# For validation
class UploadForm(forms.Form):

    picture = forms.ImageField(required=True)


class ThumbForm(forms.ModelForm):

    id = forms.IntegerField(required=False, widget=forms.HiddenInput)
    image_id = forms.IntegerField(required=False)
    orig_image = forms.CharField(max_length=512)
    orig_w = forms.IntegerField(required=False)
    orig_h = forms.IntegerField(required=False)
    sizes = forms.CharField()
    thumbs = forms.CharField(required=False)

    class Meta:
        model = Thumb
        fields = (
            'id', 'image_id', 'name', 'width', 'height',
            'orig_image', 'orig_w', 'orig_h',
            'crop_x', 'crop_y', 'crop_w', 'crop_h')

    def clean_sizes(self):
        sizes = self.cleaned_data.get('sizes')
        return json.loads(sizes)

    def clean_thumbs(self):
        thumbs = self.cleaned_data.get('thumbs')
        try:
            return json.loads(thumbs)
        except:
            return {}

    def clean(self):
        data = super(ThumbForm, self).clean()
        sizes = dict([[sz.name, sz] for sz in data['sizes']])
        name = data['name']
        try:
            data['size'] = sizes[name]
        except IndexError:
            raise ValidationError(u"Size %s is missing from sizes field" % name)
        return data


def get_admin_base_template():
    try:
        import custom_admin
    except ImportError:
        try:
            import admin_mod
        except ImportError:
            return 'admin/base.html'
        else:
            return 'admin_mod/base.html'
    else:
        return 'custom_admin/base.html'


@csrf_exempt
def upload(request):
    if request.method == "GET":
        ctx = {
            'is_popup': True,
            'image_element_id': request.GET.get('el_id', ''),
            'orig_image': '',
            'upload_to': request.GET.get('upload_to', ''),
            'thumb_name': request.GET.get('thumb_name', ''),
            'parent_template': get_admin_base_template(),
        }
        initial = {}
        thumb_ids = request.GET.get('thumbs', '')
        if thumb_ids:
            thumb_ids = filter(None, request.GET['thumbs'].split(','))
            try:
                thumb_ids = map(int, thumb_ids)
            except TypeError:
                thumb_ids = []

        thumb = Thumb(name=ctx['thumb_name'])
        if thumb_ids:
            try:
                thumb = Thumb.objects.get(pk__in=thumb_ids, name=ctx['thumb_name'])
            except Thumb.DoesNotExist:
                pass
            else:
                thumbs = Thumb.objects.filter(pk__in=thumb_ids).values('id', 'name', 'width', 'height')
                thumbs_data = dict([(t['name'], t) for t in thumbs])
                initial['thumbs'] =  json.dumps(thumbs_data)

        if request.GET.get('id'):
            try:
                image = CropDusterImage.objects.get(pk=request.GET['id'])
            except CropDusterImage.DoesNotExist:
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
                    orig_w, orig_h = img.size
                    initial.update({
                        'orig_image': orig_image,
                        'orig_w': orig_w,
                        'orig_h': orig_h,
                    })
                    ctx['image'] = preview_url

        ctx.update({
            'thumb_form': ThumbForm(instance=thumb, initial=initial, prefix='thumb'),
            'image': ctx.pop('image', u"%scropduster/img/blank.gif" % settings.STATIC_URL),
        })
        return render_to_response('cropduster/upload.html', RequestContext(request, ctx))
    else:
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
            preview_img = rescale(img, w, h, crop=False)
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

            new_orig_file_path = os.path.join(folder_path, 'original' + extension)
            os.rename(orig_file_path, new_orig_file_path)
            orig_url = get_relative_media_url(new_orig_file_path)

            preview_file_path = os.path.join(folder_path, '_preview' + extension)
            preview_img.save(preview_file_path, **img_save_params)

        data = {
            'url': get_media_url(preview_file_path),
            'orig_image': get_relative_media_url(preview_file_path),
            'orig_width': orig_w,
            'orig_height': orig_h,
            'width': w,
            'height': h,
            'orig_url': orig_url,
        }
        return HttpResponse(json.dumps(data))


@csrf_exempt
def crop(request):
    try:
        if request.method == "GET":
            raise CropDusterViewException("Form submission invalid")
    except CropDusterViewException as e:
        return json_error(request, 'crop',
            action="cropping image", errors=[e], log_error=True)

    thumb_id = request.POST.get('thumb-id')
    form_kwargs = {}
    if thumb_id:
        form_kwargs['instance'] = Thumb.objects.get(pk=thumb_id)

    form = ThumbForm(request.POST, request.FILES, prefix='thumb', **form_kwargs)
    if not form.is_valid():
        for k in sorted(form.errors.keys()):
            v = form.errors.pop(k)
            k = mark_safe('<span class="error-field error-%(k)s">%(k)s</span>' % {'k': k})
            form.errors[k] = v
        return json_error(request, 'crop', action='submitting form',
                errors=[unicode(form.errors)])
    crop_thumb = form.save(commit=False)
    data = form.cleaned_data

    db_image = CropDusterImage()
    db_image.image = data['orig_image']

    try:
        new_thumbs = db_image.save_size(data['size'], crop_thumb, tmp=True)
    except CropDusterResizeException as e:
        return json_error(request, 'crop', action='creating crops', errors=[unicode(e)])

    thumb_data = data['thumbs']
    thumb_objs = {}
    for name in thumb_data:
        try:
            thumb_objs[name] = Thumb.objects.get(pk=thumb_data[name]['id'])
        except Thumb.DoesNotExist:
            pass

    for name, thumb in new_thumbs.iteritems():
        thumb_objs[name] = thumb
        thumb_data[name] = {
            'id': thumb.pk,
            'name': name,
            'width': thumb.width,
            'height': thumb.height,
            'changed': True,
        }

    next_size = next_thumb = None
    sizes = []
    try:
        sizes = list(data['sizes'])
    except TypeError:
        pass

    for i, size in enumerate(sizes):
        if size.name == data['name']:
            try:
                next_size = sizes[i + 1]
            except IndexError:
                pass
            else:
                next_thumb = next_size.name

    try:
        pil_image = PIL.Image.open(db_image.image.path)
    except IOError:
        pil_image = None

    initial_crop = None
    if next_thumb:
        if thumb_objs.get(next_thumb) and thumb_objs[next_thumb].crop_w:
            thumb_obj = thumb_objs[next_thumb]
            initial_crop = {
                'thumb_id': thumb_obj.pk,
                'x': thumb_obj.crop_x,
                'y': thumb_obj.crop_y,
                'w': thumb_obj.crop_w,
                'h': thumb_obj.crop_h,
                'name': next_thumb,
                'initial': True,
            }
        elif thumb_objs.get(data['name']):
            old_thumb_obj = thumb_objs[data['name']]
            best_fit = next_size.fit_to_crop(old_thumb_obj, original_image=pil_image)
            if best_fit:
                initial_crop = {
                    'thumb_id': '',
                    'x': best_fit.box.x1,
                    'y': best_fit.box.y1,
                    'w': best_fit.box.w,
                    'h': best_fit.box.h,
                    'name': next_thumb,
                    'initial': True,
                }

    response_data = {
        'id': db_image.pk or data['image_id'],
        'image': db_image.image.name if db_image.image else None,
        'thumbs': thumb_data,
        'next_thumb': next_thumb,
        'initial_crop': initial_crop,
    }
    return HttpResponse(json.dumps(response_data))
