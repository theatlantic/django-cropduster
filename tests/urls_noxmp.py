"""URLconf for :mod:`tests.settings_noxmp`: tests.urls without ckeditor."""

from django.urls import include, re_path
from django.contrib import admin


admin.autodiscover()

urlpatterns = [
    re_path(r"^cropduster/", include("cropduster.urls")),
    re_path(r'^admin/', admin.site.urls),
]
