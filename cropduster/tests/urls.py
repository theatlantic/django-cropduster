from django.conf import settings
from django.conf.urls import include, url, static
from django.contrib import admin

# Explicitly import to register the admins for the test models
import cropduster.tests.admin


urlpatterns = [
    url(r"^cropduster/", include("cropduster.urls")),
    url(r'^admin/', include(admin.site.urls)),
] + static.static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

try:
    import grappelli
except ImportError:
    pass
else:
    urlpatterns += [url(r"^grappelli/", include("grappelli.urls"))]

if settings.DEBUG:
    urlpatterns += [
        url(r'^media/(?P<path>.*)$', 'django.views.static.serve', {
            'document_root': settings.MEDIA_ROOT,
        }),
    ]
