import re
import json

from jsonutil import jsonutil

from django.forms.widgets import Input
from django.conf import settings
from django.contrib.admin import helpers
from django.contrib.admin.sites import site
from django.db.models.fields.files import ImageFieldFile
from django.template.loader import render_to_string

from .admin import cropduster_inline_factory
from .models import Image
from .settings import CROPDUSTER_UPLOAD_PATH
from .utils import OrderedDict, get_aspect_ratios, get_min_size, relpath


class CropDusterWidget(Input):

    sizes = None
    auto_sizes = None
    field = None

    class Media:
        css = {'all': (u'%scropduster/css/CropDuster.css' % settings.STATIC_URL,),}
        js = (
            u'%scropduster/js/jsrender.js' % settings.STATIC_URL,
            u'%scropduster/js/CropDuster.js' % settings.STATIC_URL,
        )

    def __init__(self, field=None, sizes=None, auto_sizes=None, attrs=None):
        self.field = field
        self.sizes = sizes or self.sizes
        self.auto_sizes = auto_sizes or self.auto_sizes

        if attrs is not None:
            self.attrs = attrs.copy()
        else:
            self.attrs = {}
    
    def render(self, name, value, attrs=None, bound_field=None):
        final_attrs = self.build_attrs(attrs, type=self.input_type, name=name)
        # Whether we are rendering from the generated inline formset
        # or rendering on the actual form.
        if name.endswith('-id'):
            return u""

        obj = None
        image_value = ''

        if isinstance(value, ImageFieldFile):
            obj = value.cropduster_image
            image_value = value.name
            value = getattr(obj, 'pk', None)
        elif isinstance(value, basestring) and not value.isdigit():
            try:
                obj = Image.objects.get_by_relpath(value)
            except Image.DoesNotExist:
                obj = None
                image_value = value
                value = None
            else:
                image_value = value
                value = obj.pk
        else:
            obj = value
            try:
                value = value.pk
            except AttributeError:
                obj = None

        self.value = value
        thumbs = OrderedDict({})

        if value is None or value == "":
            final_attrs['value'] = ""
        else:
            final_attrs['value'] = value
            if obj is None:
                obj = Image.objects.get(pk=value)
            if obj is not None:
                for thumb in obj.thumbs.all().order_by('-width'):
                    size_name = thumb.name
                    thumbs[size_name] = obj.get_image_url(size_name)

        final_attrs['sizes'] = jsonutil.dumps(self.sizes)
        final_attrs['auto_sizes'] = jsonutil.dumps(self.auto_sizes)

        relative_path = relpath(settings.MEDIA_ROOT, CROPDUSTER_UPLOAD_PATH)
        if re.match(r'\.\.', relative_path):
            raise Exception("Upload path is outside of static root")

        formset = self.get_inline_admin_formset(name, value, instance=obj, bound_field=bound_field)
        return render_to_string("cropduster/custom_field.html", {
            'image_value': image_value,
            'inline_admin_formset': formset,
            'prefix': name,
            'static_url': json.dumps(u'%s/%s/' % (settings.MEDIA_URL, relative_path)),
            'min_size': jsonutil.dumps(get_min_size(self.sizes, self.auto_sizes)),
            'aspect_ratio': jsonutil.dumps(get_aspect_ratios(self.sizes)[0]),
            'final_attrs': final_attrs,
            'thumbs': thumbs,
            'image_path': u'%s/%s' % (relative_path, image_value),
        })

    def get_inline_admin_formset(self, name, value, instance=None, bound_field=None):
        formfield = getattr(bound_field, 'field', None)
        related = getattr(formfield, 'related', None)
        dbfield = getattr(related, 'field', None)

        if dbfield is None:
            return None
        request = getattr(formfield, 'request', None)
        inline_cls = cropduster_inline_factory(field=dbfield)
        inline = inline_cls(dbfield.model, site)

        FormSet = inline.get_formset(request, obj=instance)
        
        formset_kwargs = {
            'data': getattr(request, 'POST', None) or bound_field.form.data or None,
            'prefix': name,
        }
        if instance:
            formset_kwargs['instance'] = instance.content_object
            formset_kwargs['queryset'] = instance.__class__._default_manager

        formset = FormSet(**formset_kwargs)
        parent_admin = getattr(self, 'parent_admin', None)
        root_admin = getattr(parent_admin, 'root_admin', parent_admin)
        fieldsets = list(inline.get_fieldsets(request, instance))
        readonly = list(inline.get_readonly_fields(request, instance))
        return helpers.InlineAdminFormSet(inline, formset,
            fieldsets, readonly_fields=readonly, model_admin=root_admin)


def cropduster_widget_factory(sizes, auto_sizes, related=None):
    return type('CropDusterWidget', (CropDusterWidget,), {
        'sizes': sizes,
        'auto_sizes': auto_sizes,
        '__module__': CropDusterWidget.__module__,
        'related': related,
        'parent_model': getattr(related, 'model', None),
        'rel_field': getattr(related, 'field', None),
    })
