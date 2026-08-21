"""
View functions used by the cropduster dialog.

index() (defined in CropDusterIndex)
====================================

The initial page that a user sees when clicking on the "Upload Image" button.
It renders a mount point for the dialog app and the whole of the state that app
opens on, so that opening the dialog costs no round trip beyond this one.


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
from io import BytesIO
import copy

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import SuspiciousOperation
from django.forms.models import modelformset_factory
from django.http import HttpResponse
from django.middleware.csrf import get_token
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.utils.encoding import force_str
from django.utils.functional import cached_property
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.generic import View

import PIL.Image

from cropduster.conf import settings as cropduster_settings
from cropduster.files import ImageFile
from cropduster.forms import bundle_media, endpoint_urls
from cropduster.models import Image, Thumb, prime_reference_thumbs
from cropduster.renderers import get_renderer
from cropduster.resizing import Box
from cropduster.services.crop import ThumbRequest, apply_crops
from cropduster.services.payload import (
    build_payload, legacy_crop_response, payload_to_legacy)
from cropduster.services.upload import (
    adopt_standalone, min_upload_size, preview_bounds, preview_dimensions)
from cropduster.standalone import NOT_INSTALLED_MESSAGE, standalone_available
from cropduster.utils import json
from cropduster.exceptions import json_error, CropDusterResizeException, full_exc_info

from .forms import CropForm, ThumbForm, ThumbFormSet, UploadForm
from .utils import get_admin_base_template, FakeQuerySet


#: Changing any crop coordinate requires the rendition to be regenerated.
CROP_FIELDS = frozenset(['crop_x', 'crop_y', 'crop_w', 'crop_h'])

DIALOG_THUMB_FIELDS = ('id', 'name', 'width', 'height')

#: Placeholder used when the dialog has no readable image.
BLANK_IMAGE = "%scropduster/img/blank.gif"


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

    @cached_property
    def max_w(self):
        """Maximum width for a standalone crop; configured sizes have their
        own."""
        return None

    @cached_property
    def debug(self):
        return self.request.GET.get('cropduster_debug') == '1'

    @cached_property
    def image(self):
        """Return image data, or empty values if the original cannot be read."""
        orig_image = self.orig_image
        try:
            width = getattr(orig_image, 'width', None) or 0
            height = getattr(orig_image, 'height', None) or 0
            name = getattr(orig_image, 'name', None)
        except Exception:
            return (None, 0, 0, None)
        pk = getattr(self.db_image, 'pk', None) if orig_image else None
        return (name, width, height, pk)

    @cached_property
    def renderer_image(self):
        """Return the ``Image`` the configured renderer reads from."""
        name, width, height, _pk = self.image
        if not name:
            return None
        if self.db_image is not None:
            return self.db_image
        return Image(image=name, width=width, height=height)

    @cached_property
    def preview(self):
        """Return the preview URL and dimensions used by the crop canvas."""
        name, width, height, _pk = self.image
        preview_w, preview_h = preview_dimensions(
            (width, height), preview_bounds(self.preview_size))
        url = getattr(self.image_file.preview_image, 'url', None)
        if not url and name and self.db_image is not None:
            # A primary-key-only request has not resolved the preview by name.
            url = self._db_image_preview_url()
        renderer_url = None
        srcset = None
        if self.renderer_image is not None:
            renderer = get_renderer()
            renderer_url = renderer.preview_url(
                self.renderer_image, width=preview_w, height=preview_h)
            srcset = renderer.preview_srcset(
                self.renderer_image, width=preview_w, height=preview_h)
        return {
            'url': url or (BLANK_IMAGE % settings.STATIC_URL),
            'rendererUrl': renderer_url,
            'srcset': srcset,
            'w': preview_w,
            'h': preview_h,
        }

    def _db_image_preview_url(self):
        db_image = self.db_image
        try:
            if not db_image.storage.exists(db_image.get_image_path('_preview')):
                db_image.save_preview(
                    preview_w=self.preview_size[0], preview_h=self.preview_size[1])
            return db_image.get_image_url('_preview')
        except (OSError, ValueError):
            return None

    def dialog_config(self):
        """Return the server-resolved state used to initialize the dialog."""
        name, width, height, pk = self.image
        min_w, min_h = min_upload_size(self.sizes)

        return {
            'elId': self.request.GET.get('el_id') or None,
            'callbackFn': self.request.GET.get('callback_fn') or None,
            'standalone': self.is_standalone,
            'maxW': self.max_w,
            'sizes': [
                size for size in self.sizes if not getattr(size, 'is_alias', False)],
            'image': None if not name else {
                'id': pk,
                'name': name,
                'url': self._original_url(),
                'width': width,
                'height': height,
            },
            'thumbs': self.dialog_thumbs(),
            'cropThumbs': self.saved_thumbs,
            'preview': self.preview,
            'previewSize': {'w': self.preview_size[0], 'h': self.preview_size[1]},
            'minSize': {'w': min_w, 'h': min_h},
            'uploadTo': self.upload_to,
            'mediaUrl': settings.MEDIA_URL,
            'urls': endpoint_urls(),
            # `get_token()` also creates the cookie needed when the dialog is
            # opened directly or from a cached page.
            'csrfToken': get_token(self.request),
            'debug': self.debug,
        }

    def _original_url(self):
        try:
            return getattr(self.orig_image, 'url', None)
        except Exception:
            return None

    @cached_property
    def _thumb_objects(self):
        thumbs = list(self.thumbs.queryset)
        prime_reference_thumbs(thumbs)
        return thumbs

    @cached_property
    def _thumb_rows(self):
        renderer = get_renderer()
        rows = []
        for thumb in self._thumb_objects:
            row = {
                field: getattr(thumb, field)
                for field in DIALOG_THUMB_FIELDS}
            row['reference_thumb_id'] = thumb.reference_thumb_id
            if self.renderer_image is not None:
                row['renderer_url'] = renderer.url(
                    thumb, image=self.renderer_image, thumbs=self._thumb_objects)
                row['srcset'] = renderer.srcset(
                    thumb, image=self.renderer_image, thumbs=self._thumb_objects)
            else:
                row['renderer_url'] = None
                row['srcset'] = None
            rows.append(row)
        return rows

    @cached_property
    def saved_thumbs(self):
        """Return saved crops and their generated renditions, keyed by name."""
        return {
            row['name']: {field: row[field] for field in DIALOG_THUMB_FIELDS}
            for row in self._thumb_rows}

    @cached_property
    def rendered_thumbs(self):
        """Return the renderer values added to each top-level crop step."""
        return {
            row['name']: {
                'renderer_url': row['renderer_url'], 'srcset': row['srcset']}
            for row in self._thumb_rows}

    def dialog_thumbs(self):
        """One entry per size the dialog offers a crop step for, in order."""
        sizes = {size.name: size for size in self.sizes}
        references = {}
        for row in self._thumb_rows:
            references.setdefault(row['reference_thumb_id'], []).append(row['name'])

        entries = []
        for thumb in self.thumbs:
            group = {}
            rendered = self.rendered_thumbs.get(thumb.name, {})
            if thumb.pk:
                # The crop itself, and the renditions that follow it.
                for name in [thumb.name] + references.get(thumb.pk, []):
                    group[name] = self.saved_thumbs[name]
            entries.append({
                'id': thumb.pk,
                'name': thumb.name,
                'width': thumb.width,
                'height': thumb.height,
                'crop_x': thumb.crop_x,
                'crop_y': thumb.crop_y,
                'crop_w': thumb.crop_w,
                'crop_h': thumb.crop_h,
                'size': sizes.get(thumb.name),
                'thumbs': group,
                'changed': False,
                'url': self._thumb_url(thumb),
                'renderer_url': rendered.get('renderer_url'),
                'srcset': rendered.get('srcset'),
            })
        return entries

    def _thumb_url(self, thumb):
        name = self.image[0]
        if not (name and thumb.pk):
            return None
        return getattr(Image.get_file_for_size(name, thumb.name), 'url', None)

    def get(self, *args, **kwargs):
        try:
            config = self.dialog_config()
        except SuspiciousOperation as e:
            # An image named by a URL the server has been told not to fetch, or
            # a path that tries to leave the storage root.
            return json_error(self.request, 'upload', action="reading the image",
                    errors=[force_str(e)])

        return render(self.request, 'cropduster/upload.html', {
            'is_popup': True,
            'parent_template': get_admin_base_template(),
            'standalone': self.is_standalone,
            'debug': self.debug,
            'dialog_media': bundle_media(),
            'dialog_config_json': json.dumps(config),
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
