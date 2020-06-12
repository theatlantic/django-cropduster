from django.contrib import admin
from .models import Author, Article, OptionalSizes, OrphanedThumbs


admin.site.register(Author)
admin.site.register(Article)
admin.site.register(OptionalSizes)
admin.site.register(OrphanedThumbs)
