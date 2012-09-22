import inspect

from .admin import cropduster_inline_factory
from .models import Image
from django.contrib.admin.options import ModelAdmin


def patch_model_admin():

    def __init__(old_init, self, model, admin_site):
        fields = model._meta.get_m2m_with_model()
        for field, m in fields:
            if hasattr(field, 'rel') and getattr(field.rel, 'to', None) == Image:
                InlineFormSet = cropduster_inline_factory(
                    field.sizes, field.auto_sizes, field.default_thumb)
                self.inlines.append(InlineFormSet)
        old_init(self, model, admin_site);

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
