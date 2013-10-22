from django.contrib.contenttypes.generic import GenericInlineModelAdmin
from django.utils.functional import curry



def cropduster_inline_factory(field=None, **kwargs):
    from cropduster.forms import cropduster_formset_factory
    from cropduster.models import Image

    attrs = {
        'sizes': getattr(field, 'sizes', kwargs.get('sizes')),
        'model': getattr(getattr(field, 'rel', None), 'to', None) or kwargs.get('model', Image),
        'default_prefix': kwargs.get('name') or getattr(field, 'name', None),
        'field': field,
    }

    class CropDusterImageInline(GenericInlineModelAdmin):

        sizes = attrs['sizes']
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
            'fields': ('image', 'thumbs',),
        }),)

        def get_formset(self, request, obj=None):
            formset = cropduster_formset_factory(
                field=attrs['field'],
                prefix=self.default_prefix,
                sizes=self.sizes,
                model=self.model,
                formfield_callback=curry(self.formfield_for_dbfield, request=request))
            if getattr(self, 'default_prefix', None):
                formset.default_prefix = self.default_prefix
            return formset

    return CropDusterImageInline
