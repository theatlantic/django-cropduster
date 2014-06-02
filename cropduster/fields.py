from django.db import models
from django.db.models.fields import Field
from django.db.models.fields.files import ImageFileDescriptor, ImageFieldFile
from django.db.models.fields.related import ManyToManyRel, ForeignRelatedObjectsDescriptor, ManyToManyField
from django.db.models.related import RelatedObject

from generic_plus.fields import GenericForeignFileField
from generic_plus.forms import (
    generic_fk_file_formset_factory, generic_fk_file_formfield_factory,
    generic_fk_file_widget_factory)

import cropduster.settings
from .forms import CropDusterInlineFormSet, CropDusterWidget
from .utils import json


class CropDusterImageFieldFile(ImageFieldFile):

    @property
    def sizes(self):
        if callable(self.field.db_field.sizes):
            return self.field.db_field.sizes(self.instance, related=self.related_object)
        else:
            return self.field.db_field.sizes


class CropDusterImageField(models.ImageField):

    attr_class = CropDusterImageFieldFile


class CropDusterField(GenericForeignFileField):

    file_field_cls = CropDusterImageField
    file_descriptor_cls = ImageFileDescriptor
    rel_file_field_name = 'image'

    def __init__(self, verbose_name=None, **kwargs):
        sizes = kwargs.pop('sizes', None)
        if isinstance(sizes, (list, tuple)) and all([isinstance(s, dict) for s in sizes]):
            sizes = json.loads(json.dumps(sizes))
        self.sizes = sizes
        to = kwargs.pop('to', '%s.Image' % cropduster.settings.CROPDUSTER_APP_LABEL)
        kwargs.update({
            'upload_to': kwargs.pop('upload_to', None) or cropduster.settings.CROPDUSTER_MEDIA_ROOT,
        })
        super(CropDusterField, self).__init__(to, verbose_name=verbose_name, **kwargs)

    def formfield(self, **kwargs):
        factory_kwargs = {
            'sizes': kwargs.pop('sizes', None) or self.sizes,
            'related': self.related,
        }

        widget = generic_fk_file_widget_factory(CropDusterWidget, **factory_kwargs)
        formfield = generic_fk_file_formfield_factory(widget=widget, **factory_kwargs)
        kwargs.update({
            'widget': widget,
            'form_class': formfield,
        })
        return super(CropDusterField, self).formfield(**kwargs)

    def get_inline_admin_formset(self, *args, **kwargs):
        def get_formset(self, request, obj=None, **kwargs):
            formset_attrs = {'sizes': self.field.sizes, 'max_num': 1}
            formset_attrs.update(kwargs)
            return generic_fk_file_formset_factory(
                formset=CropDusterInlineFormSet,
                field=self.field,
                formset_attrs=formset_attrs,
                prefix=self.default_prefix)

        return super(CropDusterField, self).get_inline_admin_formset(
            formset_cls=CropDusterInlineFormSet,
            attrs={
                'sizes': self.sizes,
                'get_formset': get_formset,
                'field': self,
        })


class CropDusterThumbField(ManyToManyField):
    pass


class ReverseForeignRelation(ManyToManyField):
    """Provides an accessor to reverse foreign key related objects"""

    def __init__(self, to, field_name, **kwargs):
        kwargs['verbose_name'] = kwargs.get('verbose_name', None)
        kwargs['rel'] = ManyToManyRel(to,
                            related_name='+',
                            symmetrical=False,
                            limit_choices_to=kwargs.pop('limit_choices_to', None),
                            through=None)
        self.field_name = field_name

        kwargs['blank'] = True
        kwargs['editable'] = True
        kwargs['serialize'] = False
        Field.__init__(self, **kwargs)

    def m2m_db_table(self):
        return self.rel.to._meta.db_table

    def m2m_column_name(self):
        return self.field_name

    def m2m_reverse_name(self):
        return self.rel.to._meta.pk.column

    def m2m_target_field_name(self):
        return self.model._meta.pk.name

    def m2m_reverse_target_field_name(self):
        return self.rel.to._meta.pk.name

    def contribute_to_class(self, cls, name):
        self.model = cls
        super(ManyToManyField, self).contribute_to_class(cls, name)

        # Add the descriptor for the m2m relation
        field = self.rel.to._meta.get_field(self.field_name)
        setattr(cls, self.name, ForeignRelatedObjectsDescriptor(
            RelatedObject(cls, self.rel.to, field)))

    def contribute_to_related_class(self, cls, related):
        pass

    def get_internal_type(self):
        return "ManyToManyField"

    def formfield(self, **kwargs):
        from cropduster.forms import CropDusterThumbFormField

        kwargs.update({
            'form_class': CropDusterThumbFormField,
            'queryset': self.rel.to._default_manager.none(),
        })
        return super(ManyToManyField, self).formfield(**kwargs)
