from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("cropduster/", include("cropduster.urls")),
    path("_nested_admin/", include("nested_admin.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# The admin's catch-all must follow the application and development media routes.
urlpatterns += [path("", admin.site.urls)]
