from __future__ import division

import hashlib
import os
import re

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile
from django.forms.models import modelformset_factory
from django.http import HttpResponseNotAllowed
from django.shortcuts import render_to_response
from django.template import RequestContext

import PIL.Image

from cropduster.metadata import MetadataDict
from cropduster.models import Image, Size, Thumb, StandaloneImage
from cropduster.settings import CROPDUSTER_PREVIEW_WIDTH, CROPDUSTER_PREVIEW_HEIGHT
from cropduster.utils import json, get_relative_media_url

from .forms import CropForm, ThumbForm, ThumbFormSet, UploadForm, clean_upload_data
from .utils import get_admin_base_template, FakeQuerySet


def parse_xmp(file_path, upload_to=None, **kwargs):
    """
    Does *way* more than the name implies.

    @TODO: Needs cleanup
    """
    abs_file_path = os.path.join(settings.MEDIA_ROOT, file_path)
    metadata = MetadataDict(abs_file_path)
    img = PIL.Image.open(abs_file_path)
    orig_w, orig_h = img.size

    if not metadata.get('DerivedFrom'):
        raise Exception("Image does not have metadata")
    try:
        standalone = StandaloneImage.objects.get(md5=metadata['DerivedFrom'])
    except StandaloneImage.DoesNotExist:
        md5 = hashlib.md5()
        with open(abs_file_path) as f:
            image_contents = f.read()
            md5.update(image_contents)

        basepath, basename = os.path.split(file_path)
        basefile, extension = os.path.splitext(basename)
        if basefile == 'original':
            basepath, basename = os.path.split(basepath)
            basename += extension
        fake_upload_file = SimpleUploadedFile(basename, image_contents)

        file_data = clean_upload_data({
            'image': fake_upload_file,
            'upload_to': upload_to,
        })
        abs_file_path = file_data['image'].name
        file_path = get_relative_media_url(abs_file_path)

        standalone, created = StandaloneImage.objects.get_or_create(md5=md5.hexdigest().lower())
        if created:
            standalone.image = file_path
            standalone.save()
        cropduster_image, created = Image.objects.get_or_create(
            content_type=ContentType.objects.get_for_model(StandaloneImage),
            object_id=standalone.pk)
        cropduster_image.image = standalone.image.name
        cropduster_image.save()

        preview_w = kwargs.get('preview_w', CROPDUSTER_PREVIEW_WIDTH)
        preview_h = kwargs.get('preview_h', CROPDUSTER_PREVIEW_HEIGHT)
        resize_ratio = min(preview_w / orig_w, preview_h / orig_h)
        if resize_ratio < 1:
            w = int(round(orig_w * resize_ratio))
            h = int(round(orig_h * resize_ratio))
            preview_img = img.resize((w, h), PIL.Image.ANTIALIAS)
        else:
            preview_img = img
        preview_file_path = cropduster_image.get_image_path('_preview')
        img_save_params = {}
        if preview_img.format == 'JPEG':
            img_save_params['quality'] = 95
        preview_img.save(preview_file_path, **img_save_params)

        thumb = Thumb(name="crop",
            crop_x=0, crop_y=0, crop_w=orig_w, crop_h=orig_h,
            width=orig_w, height=orig_h)
        return cropduster_image, thumb, Size('crop')
    else:
        cropduster_image = standalone.image.cropduster_image
        if not getattr(cropduster_image, 'pk', None):
            raise Exception("Image does not exist in database")

    dimensions = metadata.get('Regions', {}).get('AppliedToDimensions', None)
    corrupt_metadata_exc = Exception("Corrupt metadata on image")
    if not isinstance(dimensions, dict):
        raise corrupt_metadata_exc
    w, h = dimensions.get('w'), dimensions.get('h')
    if not all(map(lambda v: isinstance(v, int), [w, h])):
        raise corrupt_metadata_exc
    region_list = metadata.get('Regions', {}).get('RegionList', [])
    if not isinstance(region_list, list):
        raise corrupt_metadata_exc
    try:
        crop_region = [r for r in region_list if r['Name'] == 'Crop'][0]
    except IndexError:
        raise corrupt_metadata_exc
    if not isinstance(crop_region, dict) or not isinstance(crop_region.get('Area'), dict):
        raise corrupt_metadata_exc
    area = crop_region.get('Area')
    # Verify that all crop area coordinates are floats
    if not all([isinstance(v, float) for k, v in area.items() if k in ('w', 'h', 'x', 'y')]):
        raise corrupt_metadata_exc

    thumb = Thumb(
        name="crop",
        crop_x=area['x'] * w,
        crop_y=area['y'] * h,
        crop_w=area['w'] * w,
        crop_h=area['h'] * h,
        width=orig_w,
        height=orig_h)

    size_w = metadata.get('size', {}).get('w') or None
    size_h = metadata.get('size', {}).get('h') or None

    return cropduster_image, thumb, Size('crop', w=size_w, h=size_h)


def standalone(request):
    if request.method == "POST":
        raise HttpResponseNotAllowed(['GET'])

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

    image_path = request.GET.get('image')
    if image_path:
        rel_image_path = get_relative_media_url(image_path, clean_slashes=False)
        if image_path != rel_image_path:
            image_path = rel_image_path
        elif re.search(r'^(?:http(?:s)?:)?//', image_path):
            # TODO: Download and save the image
            image_path = None

    upload_to = request.GET.get('upload_to') or None

    if image_path and os.path.exists(os.path.join(settings.MEDIA_ROOT, image_path)):
        image, thumb, size = parse_xmp(image_path,
                upload_to=upload_to,
                preview_w=preview_width, preview_h=preview_height)
    else:
        image, thumb, size = None, Thumb(), Size('crop')

    initial = {
        'standalone': True,
    }

    thumbs = Thumb.objects.none()
    sizes = [size]

    if not image:
        preview_url = None
    else:
        orig_w, orig_h = image.get_image_size()
        image_path = os.path.split(image.image.name)[0]
        initial.update({
            'image_id': image.pk,
            'orig_image': u'/'.join([image_path, 'original' + image.extension]),
            'orig_w': orig_w,
            'orig_h': orig_h,
        })
        preview_url = image.get_image_url('_preview')

    initial['sizes'] = json.dumps(sizes)

    # Create a fake queryset with the same order as the image `sizes`.
    # This is necessary if we want the formset thumb order to be consistent.
    fake_queryset = FakeQuerySet([thumb], thumbs)

    FormSet = modelformset_factory(Thumb, form=ThumbForm, formset=ThumbFormSet, extra=0)
    thumb_formset = FormSet(queryset=fake_queryset, initial=[], prefix='thumbs')

    for thumb_form, size in zip(thumb_formset.initial_forms, sizes):
        thumb_form.initial.update({
            'size': json.dumps(size),
            'changed': False,
        })

    return render_to_response('cropduster/upload.html', RequestContext(request, {
        'image': preview_url or u"%scropduster/img/blank.gif" % settings.STATIC_URL,
        'standalone': True,
        'is_popup': True,
        'orig_image': '',
        'parent_template': get_admin_base_template(),
        'upload_form': UploadForm(initial={
            'upload_to': upload_to,
            'sizes': initial['sizes'],
            'standalone': True,
            'preview_width': preview_width,
            'preview_height': preview_height,
        }),
        'crop_form': CropForm(initial=initial, prefix='crop'),
        'thumb_formset': thumb_formset,
    }))
