# FROM THE FUTURE LOL
from __future__ import division

import os

try:
    from collections import OrderedDict
except ImportError:
    from django.utils.datastructures import SortedDict as OrderedDict

from django import forms
from django.conf import settings
from django.http import HttpResponse, HttpResponseServerError
from django.shortcuts import render_to_response
from django.template import RequestContext
from django.core.cache import cache
from django.utils.datastructures import MultiValueDictKeyError
from django.views.decorators.csrf import csrf_exempt
from jsonutil import jsonutil

import PIL.Image

# from .handlers import UploadProgressCachedHandler
from .models import Image as CropDusterImage
from .settings import CROPDUSTER_UPLOAD_PATH
from .utils import (
    rescale, get_relative_media_url, get_upload_foldername,
    get_image_extension, get_media_path, get_media_url, get_min_size,
    create_cropped_image, relpath)
from .exceptions import json_error, CropDusterViewException

import json
import re


# For validation
class UploadForm(forms.Form):
    picture = forms.ImageField(required=True)


@csrf_exempt
def upload(request):
    if request.method == "GET":
        image_element_id = request.GET.get('el_id', '')

        context_data = {
            'is_popup': True,
            'image_element_id': image_element_id,
            'image': u"%scropduster/img/blank.gif" % settings.STATIC_URL,
            'orig_image': '',
            'x': request.GET.get('x', 0),
            'y': request.GET.get('y', 0),
            'w': request.GET.get('w', 0),
            'h': request.GET.get('h', 0),
        }

        if request.GET.get('id'):
            try:
                image = CropDusterImage.objects.get(pk=request.GET['id'])
            except CropDusterImage.DoesNotExist:
                pass
            else:
                orig_w, orig_h = image.get_image_size()
                context_data.update({
                    'image_id': image.pk,
                    'orig_image': os.path.join(image.path, 'original' + image.extension),
                    'image': image.get_image_url('_preview'),
                    'orig_w': orig_w,
                    'orig_h': orig_h,
                })

        # If we have a new image that hasn't been saved yet
        if request.GET.get('path'):
            path = request.GET['path']
            root_path = os.path.join(CROPDUSTER_UPLOAD_PATH, path)
            ext = request.GET.get('ext', '')
            if os.path.exists(os.path.join(root_path, '_preview.%s' % ext)):
                relative_url = relpath(settings.MEDIA_ROOT, CROPDUSTER_UPLOAD_PATH)
                orig_image = u"%s/original.%s" % (path, ext)
                context_data['orig_image'] = orig_image
                preview_url = u'/'.join([settings.MEDIA_URL, relative_url, path, '_preview.%s' % ext])
                # Remove double '/'s
                preview_url = re.sub(r'(?<!:)/+', '/', preview_url)
                try:
                    img = PIL.Image.open(os.path.join(settings.STATIC_ROOT, orig_image))
                except:
                    pass
                else:
                    (orig_w, orig_h) = img.size
                    context_data.update({
                        'image': preview_url,
                        'orig_w': orig_w,
                        'orig_h': orig_h,
                    })

        try:
            import custom_admin
        except ImportError:
            try:
                import admin_mod
            except ImportError:
                context_data['parent_template'] = 'admin/base.html'
            else:
                context_data['parent_template'] = 'admin_mod/base.html'
        else:
            context_data['parent_template'] = 'custom_admin/base.html'

        return render_to_response('cropduster/upload.html', RequestContext(request, context_data))
    else:
        # if hasattr(settings, 'CACHE_BACKEND'):
        #     request.upload_handlers.insert(0, UploadProgressCachedHandler(request))

        form = UploadForm(request.POST, request.FILES)

        if not form.is_valid():
            return json_error(request, 'upload', action="uploading file", errors=form['picture'].errors)

        file_ = request.FILES['picture'];
        extension = os.path.splitext(file_.name)[1].lower()
        folder_path = get_upload_foldername(file_.name)

        tmp_file_path = os.path.join(folder_path, '__tmp' + extension)

        with open(tmp_file_path, 'wb+') as f:
            for chunk in file_.chunks():
                f.write(chunk)

        img = PIL.Image.open(tmp_file_path)

        (w, h) = img.size
        (orig_w, orig_h) = img.size
        (min_w, min_h) = get_min_size(request.POST['sizes'], request.POST['auto_sizes'])

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
            'orig_width': orig_w,
            'orig_height': orig_h,
            'width': w,
            'height': h,
            'orig_url': orig_url,
        }
        return HttpResponse(json.dumps(data))


def upload_progress(request):
    """
    Return JSON object with information about the progress of an upload.
    """
    progress_id = ''
    if 'X-Progress-ID' in request.GET:
        progress_id = request.GET['X-Progress-ID']
    elif 'X-Progress-ID' in request.META:
        progress_id = request.META['X-Progress-ID']
    if progress_id:
        cache_key = "%s_%s" % (request.META['REMOTE_ADDR'], progress_id)
        data = cache.get(cache_key)
        return HttpResponse(jsonutil.dumps(data))
    else:
        return HttpResponseServerError('Server Error: You must provide X-Progress-ID header or query param.')


@csrf_exempt
def crop(request):
    try:
        if request.method == "GET":
            raise CropDusterViewException("Form submission invalid")
        path = get_media_path(request.POST['orig_image'])
    except CropDusterViewException as e:
        return json_error(request, 'crop',
            action="cropping image", errors=[e], log_error=True)
    except MultiValueDictKeyError as e:
        return json_error(request, 'crop',
            action="cropping image", errors=["Form submission contained no data"])

    #@todo Check orig_image is in fact a path before passing it to create_cropped_image
    file_root, file_ext = os.path.splitext(path)

    # all we need is the folder name, not the last file name
    file_dir, file_prefix = os.path.split(file_root)

    try:
        x = int(request.POST['x'])
        y = int(request.POST['y'])
        w = int(request.POST['w'])
        h = int(request.POST['h'])
    except TypeError as e:
        return json_error(request, 'crop', action="parsing crop parameters", errors=[e], log_error=True)

    try:
        img = create_cropped_image(path, x=x, y=y, w=w, h=h)
    except Exception as e:
        return json_error(request, 'crop', action="creating cropped image", errors=[e], log_error=True)

    rel_url_path = get_relative_media_url(request.POST['orig_image'])
    file_path, file_full_name = os.path.split(rel_url_path)

    # If the path passed matches an existing cropduster.Image, update it
    try:
        db_image = CropDusterImage.objects.get(path=file_path)
    except CropDusterImage.DoesNotExist:
        db_image = CropDusterImage()
        db_image.path = file_path
        db_image.extension = os.path.splitext(file_full_name)[1]
    db_image.crop_x = x
    db_image.crop_y = y
    db_image.crop_w = w
    db_image.crop_h = h

    try:
        sizes = jsonutil.loads(request.POST['sizes'])
        auto_sizes = jsonutil.loads(request.POST['auto_sizes'])
    except Exception as e:
        return json_error(request, 'crop', action="reading POST data", errors=[e])

    thumb_ids = OrderedDict({})

    try:
        new_ids = _generate_and_save_thumbs(db_image, sizes, img, file_dir, file_ext)
        thumb_ids.update(new_ids)
        if auto_sizes is not None:
            new_ids = _generate_and_save_thumbs(db_image, auto_sizes, img, file_dir, file_ext, is_auto=True)
            thumb_ids.update(new_ids)
    except Exception as e:
        return json_error(request, 'crop', action="generating cropped thumbnails", errors=[e])

    thumb_urls = OrderedDict({})
    for size_name in thumb_ids:
        thumb_urls[size_name] = db_image.get_image_url(size_name, use_temp=True)

    data = {
        'id': db_image.pk or request.POST.get('image_id', ''),
        'sizes': request.POST['sizes'],
        'image': request.POST['orig_image'],
        'thumb_urls': jsonutil.dumps(thumb_urls),
        'filename': os.path.split(db_image.path)[1] + db_image.extension,
        'extension': db_image._extension,
        'path': db_image.path,
        'relpath': db_image.get_relative_image_path(),
        'thumbs': jsonutil.dumps(thumb_ids),
        'x': request.POST['x'],
        'y': request.POST['y'],
        'w': request.POST['w'],
        'h': request.POST['h'],
    }
    return HttpResponse(jsonutil.dumps(data))


def _generate_and_save_thumbs(db_image, sizes, img, file_dir, file_ext, is_auto=False):
    '''
    Loops through the sizes given and saves a thumbnail for each one. Returns
    a dict of key value pairs with size_name, thumbnail_id
    '''
    thumb_ids = {}

    img_save_params = {}
    if img.format == 'JPEG':
        img_save_params['quality'] = 95

    for size_name in sizes:
        size = sizes[size_name]
        thumb_w, thumb_h = map(int, size)
        thumb = rescale(img.copy(), thumb_w, thumb_h, crop=is_auto)

        # Save to the real thumb_path if the image is new
        thumb_path = file_dir + '/' + size_name + file_ext
        if not os.path.exists(thumb_path):
            thumb.save(thumb_path, **img_save_params)

        thumb_tmp_path = file_dir + '/' + size_name + '_tmp' + file_ext

        thumb.save(thumb_tmp_path, **img_save_params)

        db_thumb = db_image.save_thumb(
            width=thumb_w,
            height=thumb_h,
            name=size_name)
        thumb_ids[size_name] = db_thumb.id

    return thumb_ids
