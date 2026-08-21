from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from project.example import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("cropduster/", include("cropduster.urls")),
    path("_nested_admin/", include("nested_admin.urls")),
    path("tiny-iframe/", views.tiny_iframe, name="tiny-iframe-add"),
    path("tiny-iframe/<int:pk>/", views.tiny_iframe, name="tiny-iframe-change"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
