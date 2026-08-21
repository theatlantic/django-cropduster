import contextlib
from operator import attrgetter

from django import forms
from django.contrib.contenttypes.admin import GenericInlineModelAdminChecks
from django.core.exceptions import FieldDoesNotExist, ImproperlyConfigured
from django.db import models, transaction, router, DEFAULT_DB_ALIAS
from django.db.models.fields.files import ImageFileDescriptor, ImageFieldFile
from django.db.models.fields.related import ManyToManyRel, ManyToManyField
from django.db.models.fields.related_descriptors import create_reverse_many_to_one_manager
from django.utils.functional import cached_property
from django.contrib.contenttypes.models import ContentType

from generic_plus.fields import GenericForeignFileField
from generic_plus.forms import (
    generic_fk_file_formset_factory, generic_fk_file_formfield_factory,
    generic_fk_file_widget_factory)

import cropduster.settings
from .conf import DIALOG_MODES
from .forms import CropDusterInlineFormSet, CropDusterWidget, CropDusterThumbFormField
from .utils import json
from .resizing import Box, Crop


class CropDusterInlineChecks(GenericInlineModelAdminChecks):
    """Run admin checks for the inline used by the Cropduster widget.

    Django reports ``admin.E013`` when a ``ManyToManyField`` has a custom
    through model. ``ReverseForeignRelation`` exposes that field API for a
    reverse foreign key, but has no through model. Its false ``through`` value
    only provides the attributes Django reads, so this check removes the
    resulting false positive.
    """

    def _check_field_spec_item(self, obj, field_name, label):
        errors = super()._check_field_spec_item(obj, field_name, label)
        if not errors:
            return errors
        try:
            field = obj.model._meta.get_field(field_name)
        except FieldDoesNotExist:
            return errors
        if not isinstance(field, ReverseForeignRelation):
            return errors
        return [e for e in errors if e.id != 'admin.E013']


class ReverseForeignRelatedObjectsRel(object):
    """Supply the relation data used by Django's reverse manager factory.

    A ``ReverseForeignRelation`` has no ``ForeignObjectRel`` of the kind that
    Django creates for a normal reverse accessor. This object provides the two
    attributes read by ``create_reverse_many_to_one_manager()``.
    """

    def __init__(self, field, related_model):
        self.field = field
        self.related_model = related_model


class CropDusterImageFieldFile(ImageFieldFile):

    @property
    def sizes(self):
        if callable(self.field.db_field.sizes):
            return self.field.db_field.sizes(self.instance, related=self.related_object)
        else:
            return self.field.db_field.sizes

    def _get_new_crop_thumb(self, size):
        # "Imports"
        Image = self.field.db_field.remote_field.model
        Thumb = Image._meta.get_field("thumbs").remote_field.model

        box = Box(0, 0, self.width, self.height)
        crop_box = Crop(box, self.name)

        best_fit = size.fit_to_crop(crop_box, original_image=self.name)
        fit_box = best_fit.box
        crop_thumb = Thumb(**{
            "name": size.name,
            "width": fit_box.w,
            "height": fit_box.h,
            "crop_x": fit_box.x1,
            "crop_y": fit_box.y1,
            "crop_w": fit_box.w,
            "crop_h": fit_box.h,
        })
        return crop_thumb

    def generate_thumbs(self, permissive=False, skip_existing=False):
        # "Imports"
        Image = self.field.db_field.remote_field.model
        Thumb = Image._meta.get_field("thumbs").remote_field.model

        has_existing_image = self.related_object is not None

        if not has_existing_image:
            obj_ct = ContentType.objects.get_for_model(
                self.instance, for_concrete_model=False)
            image = Image(**{
                'content_type': obj_ct,
                'object_id': self.instance.pk,
                'field_identifier': self.field.generic_field.field_identifier,
                'width': self.width,
                'height': self.height,
                'image': self.name,
            })
            image.save()
            self.related_object = image

        for size in self.sizes:
            if getattr(size, 'is_alias', False):
                continue
            try:
                crop_thumb = self.related_object.thumbs.get(name=size.name)
            except Thumb.DoesNotExist:
                crop_thumb = self._get_new_crop_thumb(size)

            thumbs = self.related_object.save_size(
                size, thumb=crop_thumb, permissive=permissive, skip_existing=skip_existing)

            for slug, thumb in thumbs.items():
                thumb.image = self.related_object
                thumb.save()


class CropDusterImageField(models.ImageField):

    attr_class = CropDusterImageFieldFile

    def formfield(self, *args, **kwargs):
        kwargs.pop('sizes', None)
        return super(CropDusterImageField, self).formfield(*args, **kwargs)


class CropDusterImageFileDescriptor(ImageFileDescriptor):
    """
    The same as ImageFileDescriptor, except only updates image dimensions if
    the file has changed
    """
    def __set__(self, instance, value):
        previous_file = instance.__dict__.get(self.field.name)
        super(ImageFileDescriptor, self).__set__(instance, value)

        if previous_file is not None:
            if previous_file != value:
                self.field.update_dimension_fields(instance, force=True)


class CropDusterSimpleImageField(models.ImageField):
    """
    Used for the field 'image' on cropduster.models.Image. Just overrides the
    descriptor_class to prevent unnecessary IO lookups on form submissions.
    """

    descriptor_class = CropDusterImageFileDescriptor


def _validate_dialog_mode(value):
    if value is None or value in DIALOG_MODES:
        return value
    raise ImproperlyConfigured(
        "dialog_mode must be one of %s, or None; got %r."
        % (', '.join(repr(mode) for mode in DIALOG_MODES), value))


class CropDusterField(GenericForeignFileField):

    file_field_cls = CropDusterImageField
    file_descriptor_cls = CropDusterImageFileDescriptor
    rel_file_field_name = 'image'
    field_identifier_field_name = 'field_identifier'

    def __init__(self, verbose_name=None, **kwargs):
        sizes = kwargs.pop('sizes', None)
        if isinstance(sizes, (list, tuple)) and all([isinstance(s, dict) for s in sizes]):
            sizes = json.loads(json.dumps(sizes))
        self.sizes = sizes
        to = kwargs.pop('to', '%s.Image' % cropduster.settings.CROPDUSTER_APP_LABEL)
        kwargs.update({
            'upload_to': kwargs.pop('upload_to', None) or '',
        })
        self.require_alt_text = kwargs.pop('require_alt_text', False)
        self.dialog_mode = _validate_dialog_mode(kwargs.pop('dialog_mode', None))
        super(CropDusterField, self).__init__(to, verbose_name=verbose_name, **kwargs)

    def formfield(self, **kwargs):
        factory_kwargs = {
            'sizes': kwargs.pop('sizes', None) or self.sizes,
            'related': self.remote_field,
        }

        widget = generic_fk_file_widget_factory(CropDusterWidget, **factory_kwargs)
        formfield = generic_fk_file_formfield_factory(widget=widget, **factory_kwargs)
        kwargs.update({
            'widget': widget,
            'form_class': formfield,
        })
        return super(CropDusterField, self).formfield(**kwargs)

    def get_inline_admin_formset(self, *args, **kwargs):
        for_concrete_model = self.for_concrete_model

        def get_formset(self, request, obj=None, **kwargs):
            formset_attrs = {'sizes': self.field.sizes, 'max_num': 1,
                             'require_alt_text': self.field.require_alt_text}
            formset_attrs.update(kwargs)
            return generic_fk_file_formset_factory(
                formset=CropDusterInlineFormSet,
                field=self.field,
                formset_attrs=formset_attrs,
                prefix=self.default_prefix,
                form_attrs={
                    "caption": forms.CharField(required=False),
                    "alt_text": forms.CharField(required=False),
                },
                for_concrete_model=for_concrete_model)

        return super(CropDusterField, self).get_inline_admin_formset(
            formset_cls=CropDusterInlineFormSet,
            attrs={
                'sizes': self.sizes,
                'get_formset': get_formset,
                'field': self,
                'checks_class': CropDusterInlineChecks,
            }
        )


def create_reverse_foreign_related_manager(
        superclass, rel_field, rel_model, limit_choices_to):
    attname = rel_field.remote_field.get_related_field().attname
    new_superclass = create_reverse_many_to_one_manager(
        superclass, ReverseForeignRelatedObjectsRel(rel_field, rel_model))

    class RelatedManager(new_superclass):
        def __init__(self, instance):
            super(RelatedManager, self).__init__(instance)
            self.core_filters = {
                "%s__%s" % (rel_field.name, attname): getattr(instance, attname),
            }

        def __call__(self, **kwargs):
            manager = getattr(self.model, kwargs.pop('manager'))
            manager_class = create_reverse_foreign_related_manager(
                    manager.__class__, rel_field, rel_model, limit_choices_to)
            return manager_class(self.instance)

        def get_queryset(self):
            try:
                return self.instance._prefetched_objects_cache[rel_field.related_query_name()]
            except (AttributeError, KeyError):
                qset = super(RelatedManager, self).get_queryset()
                return qset.complex_filter(limit_choices_to)

        def set(self, objs, **kwargs):
            db = router.db_for_write(self.model, instance=self.instance)
            with transaction.atomic(using=db, savepoint=False):
                super(RelatedManager, self).set(objs, **kwargs)
                for obj in objs:
                    obj.save()

        set.alters_data = True

        # Django 4.2 calls the singular form during prefetch; Django 5.0
        # deprecated it in favor of get_prefetch_querysets().
        def get_prefetch_queryset(self, instances, queryset=None):
            if queryset is None:
                return self.get_prefetch_querysets(instances)
            return self.get_prefetch_querysets(instances, [queryset])

        def get_prefetch_querysets(self, instances, querysets=None):
            if isinstance(instances[0], CropDusterImageFieldFile):
                instances = [i.related_object for i in instances]

            if querysets is None:
                queryset = super(new_superclass, self).get_queryset()
            else:
                queryset = querysets[0]

            queryset._add_hints(instance=instances[0])
            queryset = queryset.using(queryset._db or self._db)

            rel_obj_attr = attrgetter(rel_field.get_attname())
            instance_attr = attrgetter(attname)
            instances_dict = {instance_attr(inst): inst for inst in instances}
            query = {
                '%s__%s__in' % (rel_field.name, attname): set(map(instance_attr, instances)),
            }
            queryset = queryset.complex_filter(limit_choices_to).filter(**query)

            for rel_obj in queryset:
                instance = instances_dict[rel_obj_attr(rel_obj)]
                setattr(rel_obj, rel_field.name, instance)
            cache_name = rel_field.related_query_name()
            return (queryset, rel_obj_attr, instance_attr, False, cache_name, False)

    return RelatedManager


class ReverseForeignRelatedObjectsDescriptor(object):

    def __init__(self, field):
        self.field = field

    def __get__(self, instance, instance_type=None):
        if instance is None:
            return self

        return self.related_manager_cls(instance)

    def __set__(self, instance, value):
        if instance is None:
            raise AttributeError("Manager must be accessed via instance")

        manager = self.__get__(instance)
        # If the foreign key can support nulls, then completely clear the related set.
        # Otherwise, just move the named objects into the set.
        rel_field = self.field.remote_field.model._meta.get_field(self.field.field_name)
        if rel_field.null:
            manager.clear()
        manager.add(*value)

    @cached_property
    def related_manager_cls(self):
        rel_model = self.field.remote_field.model
        rel_field = rel_model._meta.get_field(self.field.field_name)
        superclass = rel_model._default_manager.__class__
        limit_choices_to = self.field.remote_field.limit_choices_to
        return create_reverse_foreign_related_manager(
            superclass, rel_field, rel_model, limit_choices_to)


class FalseThrough(object):
    """
    Django 1.7+ expects rel.through._meta.auto_created to not throw an
    AttributeError on fields that extend ManyToManyField. So we create a
    falsey object that has rel.through._meta.auto_created = False
    """

    def __nonzero__(cls):
        return False

    __bool__ = __nonzero__

    _meta = type('Options', (object,), {
        'auto_created': False,
        'managed': False,
        'local_fields': [],
    })


@contextlib.contextmanager
def rel_through_none(instance):
    """
    Temporarily set instance.rel.through to None, instead of our FalseThrough
    object.
    """
    through, instance.remote_field.through = instance.remote_field.through, None
    instance.many_to_many = False
    yield
    instance.many_to_many = True
    instance.remote_field.through = through


class ReverseForeignRelation(ManyToManyField):
    """Provides an accessor to reverse foreign key related objects"""

    # Field flags
    auto_created = False

    many_to_many = True
    many_to_one = False
    one_to_many = True
    one_to_one = False

    db_table = None
    swappable = False
    has_null_arg = False

    def __init__(self, to, field_name, **kwargs):
        is_migration = kwargs.pop('is_migration', False)
        kwargs['verbose_name'] = kwargs.get('verbose_name', None)
        m2m_rel_kwargs = {
            'related_name': None,
            'symmetrical': True,
            'limit_choices_to': kwargs.pop('limit_choices_to', None),
            'through': None,
        }

        if is_migration:
            m2m_rel_kwargs['through'] = None
            self.many_to_many = False
        else:
            m2m_rel_kwargs['through'] = FalseThrough()

        kwargs['rel'] = ManyToManyRel(self, to, **m2m_rel_kwargs)

        self.field_name = field_name

        kwargs['blank'] = True
        kwargs['editable'] = True
        kwargs['serialize'] = False
        super(ManyToManyField, self).__init__(**kwargs)

    def is_hidden(self):
        return True

    def m2m_db_table(self):
        return self.remote_field.model._meta.db_table

    def m2m_column_name(self):
        return self.remote_field.model._meta.get_field(self.field_name).attname

    def m2m_reverse_name(self):
        return self.remote_field.model._meta.pk.column

    def m2m_target_field_name(self):
        return self.model._meta.pk.name

    def m2m_reverse_target_field_name(self):
        return self.remote_field.model._meta.pk.name

    def get_attname_column(self):
        attname, column = super(ReverseForeignRelation, self).get_attname_column()
        return attname, None

    def contribute_to_class(self, cls, name, **kwargs):
        self.model = cls
        super(ManyToManyField, self).contribute_to_class(cls, name, **kwargs)

        # Add the descriptor for the reverse fk relation
        setattr(cls, self.name, ReverseForeignRelatedObjectsDescriptor(self))

    def contribute_to_related_class(self, cls, related):
        pass

    def get_internal_type(self):
        return "ManyToManyField"

    def formfield(self, **kwargs):
        kwargs.update({
            'form_class': CropDusterThumbFormField,
            'queryset': self.remote_field.model._default_manager.none(),
        })
        return super(ManyToManyField, self).formfield(**kwargs)

    def bulk_related_objects(self, objs, using=DEFAULT_DB_ALIAS):
        """
        Return all objects related to ``objs`` via this ``ReverseForeignRelation``.
        """
        rel_field_attname = self.remote_field.model._meta.get_field(self.field_name).attname
        return (
            self.remote_field.model._base_manager.db_manager(using)
                .complex_filter(self.remote_field.limit_choices_to)
                .filter(**{'%s__in' % rel_field_attname: [obj.pk for obj in objs]}))

    def related_query_name(self):
        # This method defines the name that can be used to identify this
        # related object in a table-spanning query. It uses the lower-cased
        # object_name followed by '+', which prevents its actual use.
        return '%s+' % self.opts.object_name.lower()

    def _check_relationship_model(self, from_model=None, **kwargs):
        # fields.E331 reports a many-to-many relation whose through model
        # is not installed. This relation represents a reverse foreign key
        # and has no through model, so the error does not apply.
        with rel_through_none(self):
            errors = super(ReverseForeignRelation, self)._check_relationship_model(from_model, **kwargs)
        return [e for e in errors if e.id != 'fields.E331']

    def deconstruct(self):
        with rel_through_none(self):
            name, path, args, kwargs = super(ReverseForeignRelation, self).deconstruct()
        kwargs['field_name'] = self.field_name
        kwargs['is_migration'] = True
        return name, path, args, kwargs

    def clone(self):
        new_field = super(ReverseForeignRelation, self).clone()
        new_field.many_to_many = False
        return new_field
