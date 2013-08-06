from django.contrib.contenttypes.generic import GenericInlineModelAdmin
from django.utils.functional import curry

from .models import Image
from . import forms


class BaseImageInline(GenericInlineModelAdmin):
    # These need to be overridden in the calling admin.py
    sizes = None
    auto_sizes = None
    default_thumb = None
        
    model = Image
    template = "cropduster/inline.html"
    # formset = BaseInlineFormSet
    extra = 1
    max_num = 1
    
    fieldsets = (
        ('Image', {
            'fields': ('id', 'crop_x', 'crop_y', 'crop_w', 'crop_h',
                       'path', '_extension', 'default_thumb', 'thumbs',),
        }),
    )

    def formfield_for_manytomany(self, db_field, request=None, **kwargs):
        """Override default ManyToManyField form field for thumbs."""
        if db_field.column == 'thumbs':
            kwargs['form_class'] = forms.CropDusterThumbField
            return db_field.formfield(**kwargs)
        return super(BaseImageInline, self).formfield_for_manytomany(db_field, request, **kwargs)

    def get_formset(self, request, obj=None):
        formset = forms.cropduster_formset_factory(
            sizes=self.sizes,
            auto_sizes=self.auto_sizes,
            default_thumb=self.default_thumb,
            model=self.model,
            formfield_callback=curry(self.formfield_for_dbfield, request=request))
        if getattr(self, 'default_prefix', None):
            formset.default_prefix = self.default_prefix
        return formset


def cropduster_inline_factory(sizes, auto_sizes, default_thumb, **kwargs):
    attrs = {
        'sizes': sizes,
        'auto_sizes': auto_sizes,
        'default_thumb': default_thumb,
        '__module__': BaseImageInline.__module__,
    }
    for k, v in kwargs.iteritems():
        if k not in ('model', 'formset', 'template'):
            continue
        attrs[k] = v
    return type("CropDusterImageInline", (BaseImageInline,), attrs)
