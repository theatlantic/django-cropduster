from django.contrib import admin
from .models import (
    Article, Author, OptionalSizes, OrphanedThumbs, WindowDialogField)


admin.site.register(Author)
admin.site.register(Article)
admin.site.register(OptionalSizes)
admin.site.register(OrphanedThumbs)
admin.site.register(WindowDialogField)
