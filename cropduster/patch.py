import inspect

from .admin import cropduster_inline_factory
from .models import Image
from django.contrib.admin.options import ModelAdmin
from django.contrib.admin import validation
from django.core.exceptions import ImproperlyConfigured


# Remove model field validation in check_formfield.
# The implementation is so buggy that it will be removed from django 1.6
def check_formfield(cls, model, opts, label, field):
    if getattr(cls.form, 'base_fields', None):
        try:
            cls.form.base_fields[field]
        except KeyError:
            raise ImproperlyConfigured("'%s.%s' refers to field '%s' that "
                "is missing from the form." % (cls.__name__, label, field))
    # ... model field validation would go here, in an else:

# Monkeypatch check_formfield() of django.contrib.admin.validation
validation.check_formfield = check_formfield


def get_cropduster_fields_for_model(model):
    """Returns a list of cropduster fields on a given model"""
    fields = model._meta.get_m2m_with_model()
    cropduster_fields = []
    for field, m in fields:
        if hasattr(field, 'rel'):
            rel_model = getattr(field.rel, 'to', None)
            # Only check classes, otherwise we'll get a TypeError
            if not isinstance(rel_model, type):
                continue
            if issubclass(rel_model, Image):
                cropduster_fields.append(field)
    return cropduster_fields


def patch_model_admin():

    def __init__(old_init, self, *args, **kwargs):
        if isinstance(self, ModelAdmin):
            model, admin_site = (args + (None, None))[0:2]
            if not model:
                model = kwargs.get('model')
        else:
            model = self.model

        cropduster_fields = get_cropduster_fields_for_model(model)
        for field in cropduster_fields:
            InlineFormSet = cropduster_inline_factory(field.sizes, field.auto_sizes, field.default_thumb)
            self.inlines.append(InlineFormSet)

        old_init(self, *args, **kwargs)
        # self.form = type('CropDuster%s' % self.form.__name__, (self.form,), {
        #     'bound_field_cls': CropDusterBoundField,
        #     '__module__': self.form.__module__,
        # })
        # for inline_instance in getattr(self, 'inline_instances', []):
        #     inline_instance.root_admin = self

    # def __init__(old_init, self, model, admin_site):
    #     fields = model._meta.get_m2m_with_model()
    #     for field, m in fields:
    #         if hasattr(field, 'rel') and getattr(field.rel, 'to', None) == Image:
    #             InlineFormSet = cropduster_inline_factory(
    #                 field.sizes, field.auto_sizes, field.default_thumb)
    #             self.inlines.append(InlineFormSet)
    #     old_init(self, model, admin_site);

    wrapfunc(ModelAdmin, '__init__', __init__)


def wrapfunc(obj, attr_name, wrapper, avoid_doublewrap=True):
    """
    Patch obj.<attr_name> so that calling it actually calls, instead,
    wrapper(original_callable, *args, **kwargs)
    """
    # Get the callable at obj.<attr_name>
    call = getattr(obj, attr_name)

    # optionally avoid multiple identical wrappings
    if avoid_doublewrap and getattr(call, 'wrapper', None) is wrapper:
        return

    # get underlying function (if any), and anyway def the wrapper closure
    original_callable = getattr(call, 'im_func', call)

    def wrappedfunc(*args, **kwargs):
        return wrapper(original_callable, *args, **kwargs)

    # set attributes, for future unwrapping and to avoid double-wrapping
    wrappedfunc.original = call
    wrappedfunc.wrapper = wrapper

    # rewrap staticmethod and classmethod specifically (iff obj is a class)
    if inspect.isclass(obj):
        if hasattr(call, 'im_self'):
            if call.im_self:
                wrappedfunc = classmethod(wrappedfunc)
        else:
            wrappedfunc = staticmethod(wrappedfunc)

    # finally, install the wrapper closure as requested
    setattr(obj, attr_name, wrappedfunc)


def unwrapfunc(obj, attr_name):
    """
    Undo the effects of wrapfunc(obj, attr_name, wrapper)
    """
    setattr(obj, attr_name, getattr(obj, attr_name).original)
