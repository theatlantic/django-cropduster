from django.conf import settings
from django.views.decorators.csrf import csrf_protect

from cropduster.conf import settings as cropduster_settings


class LegacyCsrfView:
    """Read ``CROPDUSTER_LEGACY_CSRF_EXEMPT`` on every request rather than
    at import."""

    def __init__(self, view):
        self.view = view
        self.protected = csrf_protect(self._call_view)
        for attr in ('__name__', '__qualname__', '__module__', '__doc__'):
            try:
                setattr(self, attr, getattr(view, attr))
            except AttributeError:
                pass

    @property
    def csrf_exempt(self):
        return cropduster_settings.CROPDUSTER_LEGACY_CSRF_EXEMPT

    def _call_view(self, request, *args, **kwargs):
        return self.view(request, *args, **kwargs)

    def __call__(self, request, *args, **kwargs):
        if self.csrf_exempt:
            return self.view(request, *args, **kwargs)
        return self.protected(request, *args, **kwargs)


def get_admin_base_template():
    if 'custom_admin' in settings.INSTALLED_APPS:
        return 'custom_admin/base.html'
    elif 'django_admin_mod' in settings.INSTALLED_APPS:
        return 'admin_mod/base.html'
    else:
        return 'admin/base.html'


class FakeQuerySet(object):

    def __init__(self, objs, queryset):
        self.objs = objs
        self.queryset = queryset

    def __iter__(self):
        return iter(self.objs)

    def __len__(self):
        return len(self.objs)

    @property
    def ordered(self):
        return True

    @property
    def db(self):
        return self.queryset.db

    def __getitem__(self, index):
        return self.objs[index]
