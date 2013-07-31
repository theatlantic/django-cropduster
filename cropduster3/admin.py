from django.contrib import admin

from .models import Size, SizeSet


class SizeInline(admin.TabularInline):
    model = Size
    prepopulated_fields = {'slug': ('name',)}
    fieldsets = (
        (None, {
            'fields': (
                'name',
                'slug',
                'width',
                'height',
                'auto_crop',
                'size_set',
                'aspect_ratio',
                'retina',
            ),
        }),
    )


class SizeSetAdmin(admin.ModelAdmin):
    prepopulated_fields = {'slug': ('name',)}
    inlines = [SizeInline]

admin.site.register(SizeSet, SizeSetAdmin)
