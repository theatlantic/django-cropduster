import nested_admin
from django.contrib import admin

from .models import Article, Gallery, Page, PageItem, PageSection, Photo, Video


@admin.register(Article)
class ArticleAdmin(nested_admin.NestedModelAdmin):
    list_display = ["title"]


@admin.register(Video)
class VideoAdmin(nested_admin.NestedModelAdmin):
    list_display = ["title"]


class PhotoInline(nested_admin.NestedStackedInline):
    model = Photo
    sortable_field_name = "position"
    extra = 0


@admin.register(Gallery)
class GalleryAdmin(nested_admin.NestedModelAdmin):
    inlines = [PhotoInline]
    list_display = ["title"]


class PageItemInline(nested_admin.NestedStackedInline):
    model = PageItem
    sortable_field_name = "position"
    extra = 0


class PageSectionInline(nested_admin.NestedStackedInline):
    model = PageSection
    sortable_field_name = "position"
    extra = 0
    inlines = [PageItemInline]


@admin.register(Page)
class PageAdmin(nested_admin.NestedModelAdmin):
    inlines = [PageSectionInline]
    list_display = ["title"]
