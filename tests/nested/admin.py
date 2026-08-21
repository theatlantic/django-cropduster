"""
Admin registrations for the nested test application.

Import ``nested_admin`` here, where ``admin.autodiscover()`` would import it
in an application. django-generic-plus depends on that import order; see the
comment in ``generic_plus/models.py``.
"""

from django.contrib import admin
from nested_admin import NestedModelAdmin, NestedStackedInline

from .models import NestedItem, NestedRoot, NestedSection


class NestedItemInline(NestedStackedInline):
    model = NestedItem
    sortable_field_name = "position"
    extra = 0


class NestedSectionInline(NestedStackedInline):
    model = NestedSection
    sortable_field_name = "position"
    extra = 0
    inlines = [NestedItemInline]


class NestedRootAdmin(NestedModelAdmin):
    inlines = [NestedSectionInline]


admin.site.register(NestedRoot, NestedRootAdmin)
