"""
URL configuration for ``tests.settings_nested``.

The patterns are declared here instead of imported from ``tests.urls``. Tests
that replace a view and reload ``settings.ROOT_URLCONF`` must also recreate
this module's ``include("cropduster.urls")`` call; reloading a module that
merely imported another URLconf would not recreate it.
"""

from django.contrib import admin
from django.urls import include, path, re_path


admin.autodiscover()

urlpatterns = [
    re_path(r"^cropduster/", include("cropduster.urls")),
    re_path(r'^ckeditor/', include('ckeditor.urls')),
    path('nested_admin/', include('nested_admin.urls')),
    re_path(r'^admin/', admin.site.urls),
]

try:
    import grappelli.urls
except ImportError:
    pass
else:
    urlpatterns += [re_path(r"^grappelli/", include(grappelli.urls))]
