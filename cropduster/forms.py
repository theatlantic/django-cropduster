import warnings

from django import forms
from django.conf import settings as django_settings
from django.core.exceptions import ValidationError
from django.forms.models import ModelChoiceIterator
from django.forms.models import ChoiceField, ModelMultipleChoiceField
from django.forms.utils import flatatt
from django.urls import NoReverseMatch, reverse
from django.utils.encoding import force_str
from django.utils.html import escape, conditional_escape, format_html

from generic_plus.forms import BaseGenericFileInlineFormSet, GenericForeignFileWidget

from .conf import settings as cropduster_settings
from .utils import json
from .utils.fields import get_cropduster_field

__all__ = (
    'CropDusterWidget', 'CropDusterThumbFormField', 'CropDusterInlineFormSet',
    'ModuleScript', 'ReactRefreshPreamble', 'bundle_media', 'endpoint_urls')


WIDGET_CSS = ('cropduster/dist/cropduster.css',)
WIDGET_JS = ('cropduster/dist/cropduster.js',)


class ModuleScript(str):

    def __html__(self):
        path = str(forms.Media().absolute_path(self))
        return format_html(
            '<script type="module" src="{}"></script>', path)


class ReactRefreshPreamble(str):
    """Inline module installing the react-refresh runtime from the dev server.

    ``@vitejs/plugin-react`` requires this preamble on pages the dev server
    does not serve itself; without it every transformed module throws
    "can't detect preamble" before the entry can run. The string value is the
    dev server's ``@react-refresh`` URL, which keeps Django's media merge
    deduplication working.
    """

    def __html__(self):
        return format_html(
            '<script type="module">'
            "import RefreshRuntime from '{}';"
            'RefreshRuntime.injectIntoGlobalHook(window);'
            'window.$RefreshReg$ = () => {{}};'
            'window.$RefreshSig$ = () => (type) => type;'
            'window.__vite_plugin_react_preamble_installed__ = true;'
            '</script>', str(self))


def bundle_media():
    dev_server = cropduster_settings.CROPDUSTER_DEV_SERVER_URL
    if django_settings.DEBUG and dev_server:
        base = '%s/' % dev_server.rstrip('/')
        return forms.Media(js=[
            ReactRefreshPreamble('%s@react-refresh' % base),
            ModuleScript('%s@vite/client' % base),
            ModuleScript('%ssrc/entry.tsx' % base),
        ])
    return forms.Media(css={'all': WIDGET_CSS}, js=WIDGET_JS)


def endpoint_urls():
    try:
        api = reverse('cropduster-api-state').removesuffix('state/')
    except NoReverseMatch:
        api = None
    return {
        'index': reverse('cropduster-index'),
        'upload': reverse('cropduster-upload'),
        'crop': reverse('cropduster-crop'),
        'api': api,
    }


class CropDusterWidget(GenericForeignFileWidget):

    sizes = None

    template = "cropduster/custom_field.html"

    @property
    def media(self):
        return bundle_media()

    def get_widget_config(self, ctx, bound_field=None):
        dbfield = getattr(
            getattr(getattr(bound_field, 'field', None), 'related', None),
            'field', None)
        if dbfield is None:
            dbfield = getattr(self, 'rel_field', None)

        config = dict(ctx.get('config') or {})
        config.update({
            'sizes': ctx['size_objects'],
            'requireAltText': bool(
                getattr(dbfield, 'require_alt_text', False)),
            'preview': {
                'url': ctx['preview_url'],
                'rendererUrl': ctx['preview_renderer_url'],
                'srcset': ctx['preview_srcset'],
                'w': ctx['preview_w'],
                'h': ctx['preview_h'],
            },
            'urls': endpoint_urls(),
            'dialogMode': cropduster_settings.CROPDUSTER_DIALOG_MODE,
            'dispatchInputEvents': True,
            'features': {'overrideSources': False},
            'target': self.get_target(dbfield, bound_field=bound_field),
            'debug': bool(django_settings.DEBUG),
        })
        return config

    def get_target(self, dbfield, bound_field=None):
        instance = getattr(
            getattr(bound_field, 'form', None), 'instance', None)
        model = type(instance) if instance is not None else getattr(
            dbfield, 'model', None)
        field_name = getattr(dbfield, 'name', None)
        if model is None or not field_name:
            return None
        object_id = getattr(instance, 'pk', None)
        return {
            'model': model._meta.label_lower,
            'objectId': object_id if isinstance(object_id, int) else (
                str(object_id) if object_id is not None else None),
            'fieldName': field_name,
        }

    def get_context_data(self, name, value, attrs=None, bound_field=None):
        ctx = super(CropDusterWidget, self).get_context_data(name, value, attrs, bound_field)
        sizes = self.sizes
        related_object = ctx['instance']
        preview_url = ''
        preview_renderer_url = ''
        preview_srcset = None
        max_preview_w = cropduster_settings.CROPDUSTER_PREVIEW_WIDTH
        max_preview_h = cropduster_settings.CROPDUSTER_PREVIEW_HEIGHT
        preview_w = max_preview_w
        preview_h = max_preview_h
        orig_w = ''
        orig_h = ''
        if related_object:
            preview_url = related_object.get_image_url(size_name='_preview')
            orig_width, orig_height = related_object.width, related_object.height
            if (orig_width and orig_height):
                orig_w, orig_h = orig_width, orig_height
                resize_ratio = min(
                    max_preview_w / float(orig_width),
                    max_preview_h / float(orig_height))
                if resize_ratio < 1:
                    preview_w = int(round(orig_width * resize_ratio))
                    preview_h = int(round(orig_height * resize_ratio))
            from cropduster.renderers import get_renderer

            renderer = get_renderer()
            preview_renderer_url = renderer.preview_url(
                related_object, width=preview_w, height=preview_h)
            preview_srcset = renderer.preview_srcset(
                related_object, width=preview_w, height=preview_h)

        if callable(sizes):
            instance = getattr(getattr(bound_field, 'form', None), 'instance', None)
            try:
                sizes_callable = sizes.__func__
            except AttributeError:
                sizes_callable = sizes
            sizes = sizes_callable(instance, related=related_object)
        sizes = [s for s in sizes if not getattr(s, 'is_alias', False)]

        ctx.update({
            'size_objects': sizes,
            'sizes': json.dumps(sizes),
            'preview_url': preview_url,
            'preview_renderer_url': preview_renderer_url,
            'preview_srcset': preview_srcset,
            'preview_w': preview_w,
            'preview_h': preview_h,
            'orig_w': orig_w,
            'orig_h': orig_h,
        })
        ctx['widget_config'] = self.get_widget_config(
            ctx, bound_field=bound_field)
        ctx['widget_config_json'] = json.dumps(ctx['widget_config'])
        return ctx


class ThumbChoiceIterator(ModelChoiceIterator):

    def __iter__(self):
        if self.field.empty_label is not None:
            yield ("", self.field.empty_label)
        if getattr(self.field, 'cache_choices', None):
            if self.field.choice_cache is None:
                self.field.choice_cache = [
                    self.choice(obj) for obj in self.queryset
                ]
            for choice in self.field.choice_cache:
                yield choice
        else:
            for obj in self.queryset:
                yield self.choice(obj)

    def choice(self, obj):
        return (obj.pk, self.field.label_from_instance(obj))


class CropDusterThumbWidget(forms.SelectMultiple):

    def __init__(self, *args, **kwargs):
        from cropduster.models import Thumb

        super(CropDusterThumbWidget, self).__init__(*args, **kwargs)
        self.model = Thumb
        self._renderer_thumbs = {}

    def get_option_attrs(self, value):
        from cropduster.renderers import get_renderer

        if isinstance(value, self.model):
            thumb = value
        else:
            try:
                thumb = self.model.objects.get(pk=value)
            except (TypeError, self.model.DoesNotExist):
                return {}

        if thumb.image_id:
            image = thumb.image
            renderer = get_renderer()
            thumb_url = image.get_image_url(size_name=thumb.name)
            renderer_url = renderer.url(thumb, image=image)
            renderer_thumbs = None
            if not renderer.supports_metadata_only:
                try:
                    renderer_thumbs = self._renderer_thumbs[image.pk]
                except KeyError:
                    renderer_thumbs = self._renderer_thumbs[image.pk] = list(
                        image.thumbs.all())
            renderer_srcset = renderer.srcset(
                thumb, image=image, thumbs=renderer_thumbs)
        else:
            thumb_url = None
            renderer_url = None
            renderer_srcset = None

        attrs = {
            'data-width': thumb.width,
            'data-height': thumb.height,
            # The stored file, byte-identical to 4.x: downstream scripts read
            # renditions from this exact attribute.
            'data-url': thumb_url,
            'data-tmp-file': json.dumps(not(thumb.image_id)),
        }
        if renderer_url:
            # What the configured renderer serves for this crop, which the
            # widget's summary card displays.
            attrs['data-renderer-url'] = renderer_url
        if renderer_srcset:
            attrs['data-renderer-srcset'] = renderer_srcset
        return attrs

    def create_option(self, *args, **kwargs):
        option = super(CropDusterThumbWidget, self).create_option(*args, **kwargs)
        option['attrs'].update(self.get_option_attrs(option['value']))
        option['selected'] = True
        if isinstance(option['value'], self.model):
            option['value'] = option['value'].pk
        return option

    def render_option(self, selected_choices, option_value, option_label):
        attrs = self.get_option_attrs(option_value)
        if isinstance(option_value, self.model):
            option_value = option_value.pk
        option_value = force_str(option_value)
        if option_value in selected_choices:
            selected_html = ' selected="selected"'
        else:
            selected_html = ''
        return (
            '<option value="%(value)s"%(selected)s%(attrs)s>%(label)s</option>') % {
                'value': escape(option_value),
                'selected': selected_html,
                'attrs': flatatt(attrs),
                'label': conditional_escape(force_str(option_label)),
        }


class CropDusterThumbFormField(ModelMultipleChoiceField):

    widget = CropDusterThumbWidget

    def clean(self, value):
        """
        Override default validation so that it doesn't throw a ValidationError
        if a given value is not in the original queryset.
        """
        try:
            value = super(CropDusterThumbFormField, self).clean(value)
        except ValidationError as e:
            if self.error_messages['required'] in e.messages:
                raise
            elif self.error_messages['list'] in e.messages:
                raise
        return value

    @property
    def choices(self):
        if not hasattr(self, '_choices'):
            return ThumbChoiceIterator(self)
        return self._choices

    @choices.setter
    def choices(self, value):
        super(self.__class__, self.__class__).choices.__set__(self, value)


def get_cropduster_field_on_model(model, field_identifier):
    """Deprecated alias for the shared Cropduster field lookup."""
    warnings.warn(
        'cropduster.forms.get_cropduster_field_on_model() is deprecated; use '
        'cropduster.utils.fields.get_cropduster_field(model, '
        'field_identifier=...) instead.',
        DeprecationWarning, stacklevel=2)
    return get_cropduster_field(model, field_identifier=field_identifier)


class CropDusterInlineFormSet(BaseGenericFileInlineFormSet):

    fields = ('image', 'thumbs', 'attribution', 'attribution_link',
        'caption', 'alt_text', 'field_identifier')

    def __init__(self, *args, **kwargs):
        super(CropDusterInlineFormSet, self).__init__(*args, **kwargs)
        if self.instance and not self.data:
            cropduster_field = get_cropduster_field(
                type(self.instance), field_identifier=self.field_identifier)
            if cropduster_field:
                # An order_by() is required to prevent the queryset result cache
                # from being removed
                self.queryset = self.queryset.order_by('pk')
                field_file = getattr(self.instance, cropduster_field.name)
                self.queryset._result_cache = list(filter(None, [field_file.related_object]))

    def clean(self):
        if any(self.errors) or not self.require_alt_text:
            # Don't bother validating the formset unless each form is valid
            # and the `require_alt_text` setting is on
            return

        for form in self.forms:
            image = form.cleaned_data.get("image")
            alt_text = form.cleaned_data.get("alt_text")

            if image and not alt_text:
                form.add_error(
                    "alt_text", "Alt text describing the image is required for this field.")

    def _construct_form(self, i, **kwargs):
        """
        Limit the queryset of the thumbs for performance reasons (so that it doesn't
        pull in every available thumbnail into the selectbox)
        """
        from cropduster.models import Thumb

        form = super(CropDusterInlineFormSet, self)._construct_form(i, **kwargs)

        field_identifier_field = form.fields['field_identifier']
        field_identifier_field.widget = forms.HiddenInput()
        field_identifier_field.initial = self.field_identifier

        thumbs_field = form.fields['thumbs']

        if form.instance and form.instance.pk:
            # Set the queryset to the current list of thumbs on the image
            thumbs_field.queryset = form.instance.thumbs.get_queryset()
        else:
            # Start with an empty queryset
            thumbs_field.queryset = Thumb.objects.none()

        if form.data:
            # Check if thumbs from POST data should be used instead.
            # These can differ from the values in the database if a
            # ValidationError elsewhere prevented saving.
            try:
                thumb_pks = [int(v) for v in form['thumbs'].value()]
            except (TypeError, ValueError):
                pass
            else:
                if thumb_pks and thumb_pks != [o.pk for o in thumbs_field.queryset]:
                    thumbs_field.queryset = Thumb.objects.filter(pk__in=thumb_pks)

        return form
