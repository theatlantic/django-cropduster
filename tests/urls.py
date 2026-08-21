from django.urls import include, re_path
from django.contrib import admin

from .views import callback_host


admin.autodiscover()

urlpatterns = [
    re_path(r"^cropduster/", include("cropduster.urls")),
    re_path(r'^ckeditor/', include('ckeditor.urls')),
    re_path(r'^admin/', admin.site.urls),
    re_path(r'^test/callback-host/$', callback_host, name='test-callback-host'),
]

try:
    import grappelli.urls
except ImportError:
    pass
else:
    urlpatterns += [re_path(r"^grappelli/", include(grappelli.urls))]
