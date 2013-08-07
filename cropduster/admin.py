from django.contrib.contenttypes.generic import GenericInlineModelAdmin
from django.utils.functional import curry



def cropduster_inline_factory(field=None, **kwargs):
    from cropduster.forms import cropduster_formset_factory, CropDusterThumbField
    from cropduster.models import Image

    attrs = {
        'sizes': getattr(field, 'sizes', kwargs.get('sizes')),
        'auto_sizes': getattr(field, 'auto_sizes', kwargs.get('auto_sizes')),
        'default_thumb': getattr(field, 'default_thumb', kwargs.get('default_thumb')),
        'model': getattr(getattr(field, 'rel', None), 'to', None) or kwargs.get('model', Image),
        'default_prefix': getattr(field, 'name', kwargs.get('name')),
        'field': field,
    }

    class CropDusterImageInline(GenericInlineModelAdmin):

        sizes = attrs['sizes']
        auto_sizes = attrs['auto_sizes']
        default_thumb = attrs['default_thumb']
        model = attrs['model']
        default_prefix = attrs['default_prefix']

        # This InlineModelAdmin exists for dual purposes: to be displayed
        # inside of the CropDusterField's widget, and as the mechanism
        # by which changes are saved when a ModelAdmin is saved. For the
        # latter purpose we would not want the inline to actually render,
        # as it would be a duplicate of the inline rendered in the
        # CropDusterField. For this reason we set the template to an
        # empty html file.
        template = "cropduster/blank.html"

        extra = 1
        max_num = 1

        fieldsets = (('Image', {
            'fields': ('crop_x', 'crop_y', 'crop_w', 'crop_h',
                       'path', '_extension', 'default_thumb', 'thumbs',),
            }),)

        def formfield_for_manytomany(self, db_field, request=None, **kwargs):
            """Override default ManyToManyField form field for thumbs."""
            if db_field.column == 'thumbs':
                kwargs['form_class'] = CropDusterThumbField
                return db_field.formfield(**kwargs)
            return super(CropDusterImageInline, self).formfield_for_manytomany(db_field, request, **kwargs)

        def get_formset(self, request, obj=None):
            formset = cropduster_formset_factory(
                field=attrs['field'],
                prefix=self.default_prefix,
                sizes=self.sizes,
                auto_sizes=self.auto_sizes,
                default_thumb=self.default_thumb,
                model=self.model,
                formfield_callback=curry(self.formfield_for_dbfield, request=request))
            if getattr(self, 'default_prefix', None):
                formset.default_prefix = self.default_prefix
            return formset

        @classmethod
        def get_default_prefix(cls):
            if cls.default_prefix:
                return cls.default_prefix
            else:
                return super(CropDusterImageInline, cls).get_default_prefix()

    return CropDusterImageInline
