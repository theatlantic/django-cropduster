import contextlib
from operator import attrgetter

import django
from django import forms
from django.db import router, models, DEFAULT_DB_ALIAS
from django.db.models.fields import Field
from django.db.models.fields.files import ImageFileDescriptor, ImageFieldFile
from django.db.models.fields.related import ManyToManyRel, ManyToManyField
from django.utils.functional import cached_property
from django.utils import six
from django.contrib.contenttypes.models import ContentType

from generic_plus.fields import GenericForeignFileField
from generic_plus.forms import (
    generic_fk_file_formset_factory, generic_fk_file_formfield_factory,
    generic_fk_file_widget_factory)

import cropduster.settings
from .forms import CropDusterInlineFormSet, CropDusterWidget, CropDusterThumbFormField
from .utils import json
from .resizing import Box, Crop

try:
    from django.db.models.fields.related import (
        create_foreign_related_manager)
except ImportError:
    try:
        from django.db.models.fields.related_descriptors import (
            create_reverse_many_to_one_manager)
    except ImportError:
        create_foreign_related_manager = None
    else:
        class ReverseForeignRelatedObjectsRel(object):

            def __init__(self, field, related_model):
                self.field = field
                self.related_model = related_model

        def create_foreign_related_manager(superclass, rel_field, rel_model):
            return create_reverse_many_to_one_manager(
                superclass, ReverseForeignRelatedObjectsRel(rel_field, rel_model))


dj19 = bool(django.VERSION >= (1, 9))


compat_rel = lambda f: getattr(f, 'remote_field' if dj19 else 'rel')
compat_rel_to = lambda f: getattr(compat_rel(f), 'model' if dj19 else 'to')


class BaseCropDusterImageFieldFile(type):
    """
    A metaclass to fix a pre-Django 1.6 bug. If the following queryset is
    attempted::

        qset.prefetch_related('image_field', 'image_field__thumbs')

    This will raise the error:

        AttributeError: Cannot find 'thumbs' on CropDusterImageFieldFile object,
        'field_name__thumbs' is an invalid parameter to prefetch_related()

    In order to have this work in Django 1.4 and 1.5, we need
    CropDusterImageFieldFile.thumbs to return a descriptor, which we proxy
    from cropduster.models.Image.thumbs.
    """

    if django.VERSION < (1, 6):
        def __getattr__(self, attr):
            if not hasattr(self, '_image_m2m_cache'):
                from cropduster.models import Image
                self._image_m2m_cache = {}
                for f in Image._meta.many_to_many:
                    self._image_m2m_cache[f.name] = getattr(Image, f.name)

            if attr in self._image_m2m_cache:
                return self._image_m2m_cache[attr]

            raise AttributeError("'%s' object has no attribute '%s'" % (
                type(self).__name__, attr))


@six.add_metaclass(BaseCropDusterImageFieldFile)
class CropDusterImageFieldFile(ImageFieldFile):

    @property
    def sizes(self):
        if six.callable(self.field.db_field.sizes):
            return self.field.db_field.sizes(self.instance, related=self.related_object)
        else:
            return self.field.db_field.sizes

    def _get_new_crop_thumb(self, size):
        # "Imports"
        Image = compat_rel_to(self.field.db_field)
        Thumb = compat_rel_to(Image._meta.get_field("thumbs"))

        box = Box(0, 0, self.width, self.height)
        crop_box = Crop(box, self.path)

        best_fit = size.fit_to_crop(crop_box, original_image=self.path)
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

    def generate_thumbs(self, permissive=False):
        # "Imports"
        Image = compat_rel_to(self.field.db_field)
        Thumb = compat_rel_to(Image._meta.get_field("thumbs"))

        has_existing_image = self.related_object is not None

        if not has_existing_image:
            ct_kwargs = {}
            if django.VERSION > (1, 5):
                ct_kwargs['for_concrete_model'] = False
            obj_ct = ContentType.objects.get_for_model(self.instance, **ct_kwargs)
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
            try:
                crop_thumb = self.related_object.thumbs.get(name=size.name)
            except Thumb.DoesNotExist:
                crop_thumb = self._get_new_crop_thumb(size)

            thumbs = self.related_object.save_size(size, thumb=crop_thumb, permissive=permissive)

            for slug, thumb in six.iteritems(thumbs):
                thumb.image = self.related_object
                thumb.save()

    if django.VERSION < (1, 6):
        # Fixes a pre-Django 1.6 bug (see the docstring of
        # BaseCropDusterImageFieldFile). We proxy attributes of the
        # related_object through the CropDusterImageFieldFile instance in
        # order to fix prefetch_related('field_name', 'field_name__thumbs')
        def __getattr__(self, attr):
            if 'related_object' in self.__dict__ and attr != 'prepare_database_save':
                try:
                    return getattr(self.__dict__['related_object'], attr)
                except AttributeError:
                    pass
            raise AttributeError("'%s' object has no attribute '%s'" % (
                type(self).__name__, attr))

        def __setattr__(self, attr, val):
            if attr == '_prefetched_objects_cache' and getattr(self, 'related_object', None):
                setattr(self.related_object, attr, val)
            else:
                super(CropDusterImageFieldFile, self).__setattr__(attr, val)


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
        super(CropDusterField, self).__init__(to, verbose_name=verbose_name, **kwargs)

    def formfield(self, **kwargs):
        factory_kwargs = {
            'sizes': kwargs.pop('sizes', None) or self.sizes,
        }
        if django.VERSION > (1, 9):
            factory_kwargs['related'] = getattr(self, 'remote_field', None)
        elif django.VERSION > (1, 8):
            factory_kwargs['related'] = getattr(self, 'rel', None)
        else:
            factory_kwargs['related'] = getattr(self, 'related', None)

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
            formset_attrs = {'sizes': self.field.sizes, 'max_num': 1}
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
            }
        )


class CropDusterThumbField(ManyToManyField):
    pass


def create_reverse_foreign_related_manager(
        superclass, rel_field, rel_model, limit_choices_to):
    attname = compat_rel(rel_field).get_related_field().attname
    if create_foreign_related_manager:
        new_superclass = create_foreign_related_manager(
            superclass, rel_field, rel_model)
    else:
        new_superclass = superclass

    class RelatedManager(new_superclass):
        def __init__(self, instance):
            if django.VERSION > (1, 7):
                super(RelatedManager, self).__init__(instance)
            else:
                super(RelatedManager, self).__init__()
                self.model = rel_model
                self.instance = instance
            self.core_filters = {
                "%s__%s" % (rel_field.name, attname): getattr(instance, attname),
            }

        if django.VERSION > (1, 8):
            def __call__(self, **kwargs):
                manager = getattr(self.model, kwargs.pop('manager'))
                manager_class = create_reverse_foreign_related_manager(
                        manager.__class__, rel_field, rel_model, limit_choices_to)
                return manager_class(self.instance)

        def get_queryset(self):
            try:
                return self.instance._prefetched_objects_cache[rel_field.related_query_name()]
            except (AttributeError, KeyError):
                if django.VERSION > (1, 6):
                    qset = super(RelatedManager, self).get_queryset()
                else:
                    qset = super(RelatedManager, self).get_query_set()
                qset = qset.complex_filter(limit_choices_to)
                if django.VERSION < (1, 7):
                    qset = qset.filter(**self.core_filters)
                return qset

        if django.VERSION < (1, 6):
            get_query_set = get_queryset

        def get_prefetch_queryset(self, instances, queryset=None):
            if isinstance(instances[0], CropDusterImageFieldFile):
                if django.VERSION > (1, 6):
                    instances = [i.related_object for i in instances]

            if queryset is None:
                if django.VERSION > (1, 7):
                    queryset = super(new_superclass, self).get_queryset()
                elif django.VERSION > (1, 6):
                    queryset = super(RelatedManager, self).get_queryset()
                else:
                    queryset = super(RelatedManager, self).get_query_set()

            if hasattr(queryset, '_add_hints'):
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
                if isinstance(instance, CropDusterImageFieldFile):
                    instance = instance.related_object
                setattr(rel_obj, rel_field.name, instance)
            cache_name = rel_field.related_query_name()
            return queryset, rel_obj_attr, instance_attr, False, cache_name

        if django.VERSION < (1, 7):
            get_prefetch_query_set = get_prefetch_queryset

        if django.VERSION < (1, 8):
            def add(self, *objs):
                for obj in objs:
                    if not isinstance(obj, self.model):
                        raise TypeError("'%s' instance expected, got %r" % (self.model._meta.object_name, obj))
                    setattr(obj, rel_field.name, self.instance)
                    obj.save()
            add.alters_data = True

            def create(self, **kwargs):
                kwargs[rel_field.name] = self.instance
                db = router.db_for_write(self.model, instance=self.instance)
                return super(RelatedManager, self.db_manager(db)).create(**kwargs)
            create.alters_data = True

            def get_or_create(self, **kwargs):
                # Update kwargs with the related object that this
                # ReverseForeignRelatedObjectsDescriptor knows about.
                kwargs[rel_field.name] = self.instance
                db = router.db_for_write(self.model, instance=self.instance)
                return super(RelatedManager, self.db_manager(db)).get_or_create(**kwargs)
            get_or_create.alters_data = True

            # remove() and clear() are only provided if the ForeignKey can have a value of null.
            if rel_field.null:
                def remove(self, *objs):
                    val = getattr(self.instance, attname)
                    for obj in objs:
                        # Is obj actually part of this descriptor set?
                        if getattr(obj, rel_field.attname) == val:
                            setattr(obj, rel_field.name, None)
                            obj.save()
                        else:
                            raise compat_rel_to(rel_field).DoesNotExist("%r is not related to %r." % (obj, self.instance))
                remove.alters_data = True

                def clear(self):
                    self.update(**{rel_field.name: None})
                clear.alters_data = True

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
        rel_field = compat_rel_to(self.field)._meta.get_field(self.field.field_name)
        if rel_field.null:
            manager.clear()
        manager.add(*value)

    @cached_property
    def related_manager_cls(self):
        # Dynamically create a class that subclasses the related model's default
        # manager.
        rel_model = compat_rel_to(self.field)
        rel_field = rel_model._meta.get_field(self.field.field_name)
        superclass = rel_model._default_manager.__class__
        limit_choices_to = compat_rel(self.field).limit_choices_to
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
    through, compat_rel(instance).through = compat_rel(instance).through, None
    instance.many_to_many = False
    yield
    instance.many_to_many = True
    compat_rel(instance).through = through


class ReverseForeignRelation(ManyToManyField):
    """Provides an accessor to reverse foreign key related objects"""

    # Field flags
    auto_created = False

    if django.VERSION > (1, 8):
        many_to_many = True
    else:
        many_to_many = False
    many_to_one = False
    one_to_many = True
    one_to_one = False

    db_table = None
    swappable = False
    if django.VERSION > (1, 8):
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

        if django.VERSION > (1, 8):
            if is_migration:
                m2m_rel_kwargs['through'] = None
                self.many_to_many = False
            else:
                m2m_rel_kwargs['through'] = FalseThrough()

            kwargs['rel'] = ManyToManyRel(self, to, **m2m_rel_kwargs)
        else:
            if django.VERSION > (1, 7):
                m2m_rel_kwargs['through'] = FalseThrough()
            kwargs['rel'] = ManyToManyRel(to, **m2m_rel_kwargs)

        self.field_name = field_name

        kwargs['blank'] = True
        kwargs['editable'] = True
        kwargs['serialize'] = False
        Field.__init__(self, **kwargs)

    def is_hidden(self):
        return True

    def m2m_db_table(self):
        return compat_rel_to(self)._meta.db_table

    def m2m_column_name(self):
        return compat_rel_to(self)._meta.get_field(self.field_name).attname

    def m2m_reverse_name(self):
        return compat_rel_to(self)._meta.pk.column

    def m2m_target_field_name(self):
        return self.model._meta.pk.name

    def m2m_reverse_target_field_name(self):
        return compat_rel_to(self)._meta.pk.name

    def get_attname_column(self):
        attname, column = super(ReverseForeignRelation, self).get_attname_column()
        return attname, None

    def contribute_to_class(self, cls, name, **kwargs):
        if (1, 8) < django.VERSION < (1, 10):
            kwargs['virtual_only'] = True
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
            'queryset': compat_rel_to(self)._default_manager.none(),
        })
        return super(ManyToManyField, self).formfield(**kwargs)

    def bulk_related_objects(self, objs, using=DEFAULT_DB_ALIAS):
        """
        Return all objects related to ``objs`` via this ``ReverseForeignRelation``.
        """
        rel_field_attname = compat_rel_to(self)._meta.get_field(self.field_name).attname
        return (
            compat_rel_to(self)._base_manager.db_manager(using)
                .complex_filter(compat_rel(self).limit_choices_to)
                .filter(**{'%s__in' % rel_field_attname: [obj.pk for obj in objs]}))

    def related_query_name(self):
        # This method defines the name that can be used to identify this
        # related object in a table-spanning query. It uses the lower-cased
        # object_name followed by '+', which prevents its actual use.
        return '%s+' % self.opts.object_name.lower()

    def _check_relationship_model(self, from_model=None, **kwargs):
        # Override error in Django 1.7 (fields.E331: "Field specifies a
        # many-to-many relation through model 'None', which has not been
        # installed"), which is spurious for a reverse foreign key field.
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
