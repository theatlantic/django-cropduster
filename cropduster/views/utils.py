def get_admin_base_template():
    try:
        import django_admin_mod
    except ImportError:
        pass
    else:
        return 'admin_mod/base.html'

    try:
        import custom_admin
    except ImportError:
        return 'admin/base.html'
    else:
        return 'custom_admin/base.html'


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
