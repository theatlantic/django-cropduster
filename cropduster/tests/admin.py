from django.contrib import admin
from .models import Author, Article, TestForOptionalSizes


admin.site.register(Author)
admin.site.register(Article)
admin.site.register(TestForOptionalSizes)
