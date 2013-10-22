import collections
from .utils import monkeypatch


def patch_django():
    patch_model_form()
    patch_model_admin()


def patch_model_form():
    from django.forms import BaseForm
    from django.forms.forms import BoundField
    from cropduster.forms import CropDusterFormField, CropDusterBoundField

    @monkeypatch(BaseForm)
    def __getitem__(old_func, self, name):
        """
        Returns a CropDusterBoundField instead of BoundField for CropDusterFormFields
        """
        try:
            field = self.fields[name]
        except KeyError:
            raise KeyError('Key %r not found in Form' % name)
        if isinstance(field, CropDusterFormField):
            return CropDusterBoundField(self, field, name)
        else:
            return BoundField(self, field, name)


def patch_model_admin(BaseModelAdmin=None, ModelAdmin=None, InlineModelAdmin=None):
    from cropduster.admin import cropduster_inline_factory
    from cropduster.models import CropDusterField

    if not BaseModelAdmin:
        from django.contrib.admin.options import BaseModelAdmin
    if not ModelAdmin:
        from django.contrib.admin.options import ModelAdmin
    if not InlineModelAdmin:
        from django.contrib.admin.options import InlineModelAdmin

    def get_cropduster_fields_for_model(model):
        """Returns a list of cropduster fields on a given model"""
        opts = model._meta
        return [f for f, m in opts.get_m2m_with_model() if isinstance(f, CropDusterField)]

    @monkeypatch([ModelAdmin, InlineModelAdmin])
    def __init__(old_init, self, *args, **kwargs):
        if isinstance(self, ModelAdmin):
            model, admin_site = (args + (None, None))[0:2]
            if not model:
                model = kwargs.get('model')
        else:
            model = self.model

        cropduster_fields = get_cropduster_fields_for_model(model)
        if len(cropduster_fields):
            # ModelAdmin.inlines is defined as a mutable on that
            # class, so we need to copy it before we append.
            # (otherwise we'll modify the `inlines` attribute for
            # all ModelAdmins).
            inlines = getattr(self, 'inlines', [])
            if isinstance(inlines, collections.MutableSequence):
                self.inlines = list(inlines)
            else:
                self.inlines = []
        for field in cropduster_fields:
            InlineFormSet = cropduster_inline_factory(field=field)
            self.inlines.append(InlineFormSet)

        old_init(self, *args, **kwargs)

    @monkeypatch(BaseModelAdmin)
    def formfield_for_dbfield(old_func, self, db_field, **kwargs):
        if isinstance(db_field, CropDusterField):
            return db_field.formfield(parent_admin=self, **kwargs)
        return old_func(self, db_field, **kwargs)
