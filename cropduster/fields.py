from django.db import models, router
from django.db.models.fields.related import (
    add_lazy_relation, create_many_to_many_intermediary_model,
    ReverseManyRelatedObjectsDescriptor)
from django.db.models.fields.files import ImageFileDescriptor, ImageFieldFile
from django.utils.functional import curry

from generic_plus.fields import GenericForeignFileField
from generic_plus.forms import (
    generic_fk_file_formset_factory, generic_fk_file_formfield_factory,
    generic_fk_file_widget_factory)

import cropduster.settings
from .forms import CropDusterInlineFormSet, CropDusterThumbFormField, CropDusterWidget
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


class ReverseManyRelatedObjectsDescriptor(ReverseManyRelatedObjectsDescriptor):
    """
    Implements the patch at https://code.djangoproject.com/ticket/6707#comment:15

    The effect of this patch is that, unlike current django (~1.6dev), m2m_changed
    is only fired when the ManyToManyField is passed new through rows, and the
    list of their ids (pk_set) in the m2m_changed signal is limited only to the
    through rows being added.
    """

    def _check_new_ids(self, manager, objs):
        new_ids = set()
        for obj in objs:
            if isinstance(obj, manager.model):
                if not router.allow_relation(obj, manager.instance):
                    raise ValueError('Cannot add "%r": instance is on database "%s", value is on database "%s"' %
                                       (obj, manager.instance._state.db, obj._state.db))
                new_ids.add(obj.pk)
            elif isinstance(obj, models.Model):
                raise TypeError("'%s' instance expected, got %r" % (manager.model._meta.object_name, obj))
            else:
                obj = self.field.rel.to._meta.pk.get_prep_value(obj)
                new_ids.add(obj)
        return new_ids

    def __set__(self, instance, value):
        if instance is None:
            raise AttributeError("Manager must be accessed via instance")

        if not self.field.rel.through._meta.auto_created:
            opts = self.field.rel.through._meta
            raise AttributeError((
                "Cannot set values on a ManyToManyField which specifies an "
                "intermediary model.  Use %s.%s's Manager instead."
              ) % (opts.app_label, opts.object_name))

        mgr = self.__get__(instance)
        if value:
            new_ids = self._check_new_ids(mgr, value)
            old_ids = set(self._check_new_ids(mgr, mgr.values_list('pk', flat=True)))
            mgr.remove(*(old_ids - new_ids))
            add_ids = new_ids - old_ids
            # Check for duplicates
            db = router.db_for_write(self.field.rel.through, instance=instance)
            vals = mgr.through._default_manager.using(db).values_list(mgr.target_field_name, flat=True)
            vals = vals.filter(**{
                mgr.source_field_name: mgr._pk_val,
                ('%s__in' % mgr.target_field_name): add_ids,
            })
            add_ids = add_ids - set(self._check_new_ids(mgr, vals))
            mgr.add(*add_ids)
        else:
            mgr.clear()


class CropDusterThumbField(models.ManyToManyField):

    def contribute_to_class(self, cls, name):
        """
        Identical to super's contribute_to_class, except that it uses the above
        ReverseManyRelatedObjectsDescriptor as the descriptor class rather
        than the class in django.db.models.fields.related of the same name

        Besides the setattr(cls, self.name, ...) line, this logic is identical
        to what can be found in ManyToManyField.contribute_to_class(). We
        cannot call the super() and then override the descriptor here, because
        then it would be using ReverseManyRelatedObjectsDescriptor.__set__(),
        so we need to call the super of ManyToManyField and duplicate all of
        the logic in ManyToManyField.contribute_to_class().
        """
        if self.rel.symmetrical and (self.rel.to in ("self", cls._meta.object_name)):
            self.rel.related_name = "%s_rel_+" % name

        super(models.ManyToManyField, self).contribute_to_class(cls, name)

        if not self.rel.through and not cls._meta.abstract:
            self.rel.through = create_many_to_many_intermediary_model(self, cls)

        # Add the descriptor for the m2m relation
        setattr(cls, self.name, ReverseManyRelatedObjectsDescriptor(self))

        self.m2m_db_table = curry(self._get_m2m_db_table, cls._meta)

        if isinstance(self.rel.through, basestring):
            def resolve_through_model(field, model, cls):
                field.rel.through = model
            add_lazy_relation(cls, self, self.rel.through, resolve_through_model)

        if isinstance(self.rel.to, basestring):
            target = self.rel.to
        else:
            target = self.rel.to._meta.db_table
        cls._meta.duplicate_targets[self.column] = (target, "m2m")

    def formfield(self, **kwargs):
        from cropduster.models import Thumb

        kwargs.update({
            'form_class': CropDusterThumbFormField,
            'queryset': Thumb.objects.none(),
        })
        return super(CropDusterThumbField, self).formfield(**kwargs)
