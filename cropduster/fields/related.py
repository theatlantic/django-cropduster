"""
Defines CropDusterGenericRelation, a subclass of GenericRelation from
django.contrib.contenttypes, which is the base class for
cropduster.fields.CropDusterField.
"""
from django.core.exceptions import ObjectDoesNotExist
from django.core.files.base import File
from django.db import connection, router, models
from django.db.models.fields.files import FieldFile, ImageFileDescriptor
from django.contrib.contenttypes.generic import GenericRelation, GenericRel

from cropduster.settings import CROPDUSTER_MEDIA_ROOT


class CropDusterGenericRelation(GenericRelation):
    """
    The base class for CropDusterField; adds descriptors to the model.

    This field accepts the same keyword arguments as models.ImageField.

    If assigned to a model with name ``field_name``, allows retrieval of
    cropduster image information by several attributes (via descriptors):

    getattr(instance, field_name):
            An instance of ImageFieldFile, with obj.field_name.cropduster_image
            as the related cropduster.Image instance (or None if there is no
            related cropduster.Image). A getattr on ``field_name`` will
            perform a database query.
    getattr(instance, '%%s_raw' %% field_name):
            An instance of ImageFieldFile that does not sync with
            cropduster.Image. Use this if you need to retrieve the image path
            but do not want to make a database query.
    getattr(instance, '%%s_generic_rel' %% field_name):
            The generic related manager for the field.
    """
    image_kwargs = None
    image_field = None

    generic_descriptor = None
    image_descriptor = None

    def __init__(self, to, **kwargs):
        self.image_kwargs = {
            'editable': False,
            'default': '',
            'blank': True,
            'upload_to': kwargs.pop('upload_to', CROPDUSTER_MEDIA_ROOT),
            'storage': kwargs.pop('storage', None),
            'width_field': kwargs.pop('width_field', None),
            'height_field': kwargs.pop('height_field', None),
            'max_length': kwargs.pop('max_length', 100),
            'db_index': kwargs.pop('db_index', False),
        }

        kwargs['rel'] = GenericRel(to,
                            related_name=kwargs.pop('related_name', None),
                            limit_choices_to=kwargs.pop('limit_choices_to', None),
                            symmetrical=kwargs.pop('symmetrical', True))

        # Override content-type/object-id field names on the related class
        self.object_id_field_name = kwargs.pop("object_id_field", "object_id")
        self.content_type_field_name = kwargs.pop("content_type_field", "content_type")

        kwargs.update({
            'blank': True,
            'editable': True,
            'serialize': False,
            'max_length': self.image_kwargs['max_length'],
        })

        models.Field.__init__(self, **kwargs)

        self.image_kwargs['db_column'] = kwargs.get('db_column', self.name)

    def __get__(self, instance, obj_type):
        try:
            return super(GenericRelation, self).__get__(instance, obj_type)
        except AttributeError:
            return self

    def contribute_to_class(self, cls, name):
        self.generic_rel_name = '%s_generic_rel' % name
        self.raw_image_field_name = '%s_raw' % name
        super(GenericRelation, self).contribute_to_class(cls, name)
        self.image_field_name = name

        # Save a reference to which model this class is on for future use
        self.model = cls

        self.__dict__['image_field'] = models.ImageField(**self.image_kwargs)
        ### HACK: manually fix creation counter
        self.image_field.creation_counter = self.creation_counter

        # This calls contribute_to_class() for the ImageField
        cls.add_to_class(self.image_field_name, self.image_field)

        # Add the descriptor for the generic relation
        generic_descriptor = CropDusterDescriptor(self, self.image_field)
        # We use self.__dict__ to avoid triggering __get__()
        self.__dict__['generic_descriptor'] = generic_descriptor
        setattr(cls, self.generic_rel_name, generic_descriptor)

        # Add the descriptor for the image field
        image_descriptor = CropDusterDescriptor(self, self.image_field,
            is_image_field=True)
        self.__dict__['image_descriptor'] = image_descriptor
        setattr(cls, self.image_field_name, image_descriptor)

        self.image_field.__dict__.update({
            'generic_descriptor': generic_descriptor,
            'image_descriptor': image_descriptor,
            'db_field': self,
            'generic_field': getattr(cls, self.generic_rel_name),
        })
        setattr(cls, self.raw_image_field_name, ImageFileDescriptor(self.image_field))


    def south_init(self):
        """
        This method is called by south before it introspects the field.

        South assumes that this is a related field if self.rel is set and it
        is not None. While this is a reasonable assumption, and it is *mostly*
        true for CropDusterField, it is incorrect as far as South is
        concerned; we need South to treat this as a FileField so that
        it creates a column in the containing model.

        To deal with this situation we conditionally return the same values as
        FileField from get_internal_type() and db_type() while south is
        introspecting the field, and otherwise return the values that would be
        returned by a GenericRelation (which are the same as those returned
        by a ManyToManyField)

        self.south_executing is the basis for the conditional logic. It is set
        to True in this method (south_init()) and then back to False in
        CropDusterGenericRelation.post_create_sql().
        """
        self.south_executing = True
        self._rel = self.rel
        self.rel = None

    def post_create_sql(self, style, db_table):
        """
        This method is called after south is done introspecting the field.

        See CropDusterGenericRelation.south_init() for more documentation
        about the reason this is overridden here.        
        """
        self.south_executing = False
        if self.rel is None and hasattr(self, '_rel'):
            self.rel = self._rel
        return []

    def get_internal_type(self):
        """
        Related to the implementation of db_type(), returns the pre-existing
        Django Field class whose database column is the same as the current
        field class, if such a class exists.

        See CropDusterGenericRelation.south_init() for more documentation
        about the reason this is overridden here.
        """
        if self.south_executing:
            return 'FileField'
        else:
            # super() returns 'ManyToManyField'
            return super(CropDusterGenericRelation, self).get_internal_type()

    def db_type(self, connection):
        """
        Returns the database column data type for this field, for the provided
        connection.

        See CropDusterGenericRelation.south_init() for more documentation
        about the reason this is overridden here.
        """
        if self.south_executing:
            return models.Field.db_type(self, connection)
        else:
            # super() returns None
            return super(CropDusterGenericRelation, self).db_type(connection)


class CropDusterDescriptor(object):

    def __init__(self, field, image_field, is_image_field=False):
        self.field = field
        self.image_field = image_field
        self.is_image_field = is_image_field

    def __get__(self, instance, instance_type=None):
        if instance is None:
            if self.is_image_field:
                return self.image_field
            else:
                return self.field

        cache_name = self.field.get_cache_name()
        image_val = None

        try:
            if self.is_image_field:
                image_val = instance.__dict__[self.image_field.name]
                raise AttributeError("Lookup related field")
            else:
                return getattr(instance, cache_name)
        except AttributeError:
            # This import is done here to avoid circular import importing this module
            from django.contrib.contenttypes.models import ContentType

            # Dynamically create a class that subclasses the related model's
            # default manager.
            rel_model = self.field.rel.to
            superclass = rel_model._default_manager.__class__
            RelatedManager = create_generic_related_manager(superclass)

            qn = connection.ops.quote_name

            if hasattr(instance._default_manager, 'prefetch_related'):
                # Django 1.4+
                manager_kwargs = {
                    'prefetch_cache_name': self.field.attname,
                }
            else:
                # Django <= 1.3
                manager_kwargs = {
                    'join_table': qn(self.field.m2m_db_table()),
                }

            manager = RelatedManager(
                model=rel_model,
                instance=instance,
                field=self.field,
                symmetrical=(self.field.rel.symmetrical and instance.__class__ == rel_model),
                source_col_name=qn(self.field.m2m_column_name()),
                target_col_name=qn(self.field.m2m_reverse_name()),
                content_type=ContentType.objects.db_manager(instance._state.db).get_for_model(instance),
                content_type_field_name=self.field.content_type_field_name,
                object_id_field_name=self.field.object_id_field_name,
                **manager_kwargs)

            if not manager.pk_val:
                val = None
            else:
                db = manager._db or router.db_for_read(rel_model, instance=instance)
                query = manager.core_filters or {
                    '%s__pk' % manager.content_type_field_name : manager.content_type.id,
                    '%s__exact' % manager.object_id_field_name : manager.pk_val,
                }

                try:
                    prev_object_id_field = rel_model._meta.get_field(
                        'prev_%s' % manager.object_id_field_name)
                except models.FieldDoesNotExist:
                    pass
                else:
                    query['%s__isnull' % prev_object_id_field.attname] = True

                qset = superclass.get_query_set(manager).using(db)

                try:            
                    val = qset.get(**query)
                except rel_model.DoesNotExist:
                    if not self.is_image_field:
                        return None
                    val = None

            if val:
                setattr(instance, cache_name, manager)
                if not self.is_image_field:
                    return manager

        self.set_image_value(instance, image_val, obj=val)
        return instance.__dict__[self.image_field.name]

    def set_image_value(self, instance, value, obj=None):
        # Sort out what to do with the image_val
        # For reference, see django.db.models.fields.files.FileDescriptor, upon
        # which this logic is based.

        # If this value is a string (instance.file = "path/to/file") or None
        # then we simply wrap it with the appropriate attribute class according
        # to the file field. [This is FieldFile for FileFields and
        # ImageFieldFile for ImageFields; it's also conceivable that user
        # subclasses might also want to subclass the attribute class]. This
        # object understands how to convert a path to a file, and also how to
        # handle None.
        attr_cls = self.image_field.attr_class
        if isinstance(value, basestring) or value is None:
            attr = attr_cls(instance, self.image_field, value)
            attr.cropduster_image = obj
            instance.__dict__[self.image_field.name] = attr

        # Other types of files may be assigned as well, but they need to have
        # the FieldFile interface added to the. Thus, we wrap any other type of
        # File inside a FieldFile (well, the field's attr_class, which is
        # usually FieldFile).
        elif isinstance(value, File) and not isinstance(value, FieldFile):
            file_copy = attr_cls(instance, self.image_field, value.name)
            file_copy.file = value
            file_copy.cropduster_image = obj
            file_copy._committed = False
            instance.__dict__[self.image_field.name] = file_copy

        # Finally, because of the (some would say boneheaded) way pickle works,
        # the underlying FieldFile might not actually itself have an associated
        # file. So we need to reset the details of the FieldFile in those cases.
        elif isinstance(value, FieldFile):
            value.instance = instance
            value.field = self.image_field
            value.storage = self.image_field.storage
            value.cropduster_image = obj
            instance.__dict__[self.image_field.name] = value

    def __set__(self, instance, value):
        from cropduster.models import Image

        if instance is None:
            raise AttributeError("Manager must be accessed via instance")
        if self.is_image_field:
            self.set_image_value(instance, value)
        else:
            manager = self.__get__(instance)
            manager.clear()
            if value is None:
                return
            if isinstance(value, Image):
                image_val = value.image.path if value.image else None
                setattr(instance, self.field.image_field_name, image_val)
                manager.add(value)
            else:
                for obj in value:
                    image_val = obj.image.path if obj.image else None
                    setattr(instance, self.field.image_field_name, image_val)
                    manager.add(obj)


def create_generic_related_manager(superclass):
    """
    Factory function for a manager that subclasses 'superclass' (which is a
    Manager) and adds behavior for generic related objects.
    """

    class GenericRelatedObjectManager(superclass):
        def __init__(self, model=None, instance=None, symmetrical=None,
                     source_col_name=None, target_col_name=None, content_type=None,
                     content_type_field_name=None, object_id_field_name=None, **kwargs):
            super(GenericRelatedObjectManager, self).__init__()
            self.model = model
            self.content_type = content_type
            self.symmetrical = symmetrical
            self.instance = instance
            if 'join_table' in kwargs:
                # django <= 1.3
                self.join_table = kwargs.pop('join_table')
                self.join_table = model._meta.db_table
                self.core_filters = kwargs.pop('core_filters', None) or {}
            else:
                # django 1.4+
                self.core_filters = {
                    '%s__pk' % content_type_field_name: content_type.id,
                    '%s__exact' % object_id_field_name: instance._get_pk_val(),
                }
            if 'prefetch_cache_name' in kwargs:
                # django 1.4+
                self.prefetch_cache_name = kwargs['prefetch_cache_name']
            self.source_col_name = source_col_name
            self.target_col_name = target_col_name
            self.content_type_field_name = content_type_field_name
            self.object_id_field_name = object_id_field_name
            self.pk_val = self.instance._get_pk_val()
            # Change from django.contrib.contenttypes.generic.create_generic_related_manager()
            self._field = kwargs.pop('field', None)
            self.image_field_name = self._field.image_field_name

        def get_query_set(self):
            if hasattr(self, 'prefetch_cache_name'):
                try:
                    return self.instance._prefetched_objects_cache[self.prefetch_cache_name]
                except (AttributeError, KeyError):
                    pass
            db = self._db or router.db_for_read(self.model, instance=self.instance)
            query = {
                '%s__pk' % self.content_type_field_name : self.content_type.id,
                '%s__exact' % self.object_id_field_name : self.pk_val,
            }
            return superclass.get_query_set(self).using(db).filter(**query)

        def get_prefetch_query_set(self, instances):
            from operator import attrgetter
            db = self._db or router.db_for_read(self.model, instance=instances[0])
            query = {
                '%s__pk' % self.content_type_field_name: self.content_type.id,
                '%s__in' % self.object_id_field_name:
                    set(obj._get_pk_val() for obj in instances)
                }
            qs = super(GenericRelatedObjectManager, self).get_query_set().using(db).filter(**query)
            return (qs,
                    attrgetter(self.object_id_field_name),
                    lambda obj: obj._get_pk_val(),
                    False,
                    self.prefetch_cache_name)

        def add(self, *objs):
            for obj in objs:
                if not isinstance(obj, self.model):
                    raise TypeError("'%s' instance expected" % self.model._meta.object_name)
                setattr(obj, self.content_type_field_name, self.content_type)
                setattr(obj, self.object_id_field_name, self.pk_val)
                obj.save()
                related_obj = self.__get_related_obj()
                setattr(related_obj, self.image_field_name, obj.path)
        add.alters_data = True

        @property
        def field(self):
            related_obj = self.__get_related_obj()
            return related_obj._meta.get_field(self.image_field_name)

        def __get_related_obj(self):
            related_cls = self.content_type.model_class()
            related_obj = related_cls.objects.get(pk=self.pk_val)
            return related_obj

        def remove(self, *objs):
            db = router.db_for_write(self.model, instance=self.instance)
            for obj in objs:
                obj.delete(using=db)
            try:
                related_obj = self.__get_related_obj()
            except ObjectDoesNotExist:
                pass
            else:
                setattr(related_obj, self.image_field_name, None)
        remove.alters_data = True

        def clear(self):
            db = router.db_for_write(self.model, instance=self.instance)
            for obj in self.all():
                obj.delete(using=db)
            related_obj = self.__get_related_obj()
            setattr(related_obj, self.image_field_name, None)
        clear.alters_data = True

        def create(self, **kwargs):
            kwargs[self.content_type_field_name] = self.content_type
            kwargs[self.object_id_field_name] = self.pk_val
            db = router.db_for_write(self.model, instance=self.instance)
            super_ = super(GenericRelatedObjectManager, self).using(db)
            new_obj = super_.create(**kwargs)
            if new_obj.path:
                related_obj = self.__get_related_obj()
                setattr(related_obj, self.image_field_name, new_obj.path)
            return new_obj
        create.alters_data = True

    return GenericRelatedObjectManager
