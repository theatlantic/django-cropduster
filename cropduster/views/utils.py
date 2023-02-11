from django.conf import settings


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
        obj_iter = iter(self.objs)
        while True:
            try:
                yield obj_iter.next()
            except StopIteration:
                break

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
