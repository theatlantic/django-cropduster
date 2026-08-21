"""Versioned JSON API routes included below Cropduster's ``api/`` path.

The version is part of each URL so different versions can be served together.
"""

from django.urls import path

from cropduster.api import views


urlpatterns = [
    path('v1/state/', views.state, name='cropduster-api-state'),
    path('v1/upload/', views.upload, name='cropduster-api-upload'),
    path('v1/crop/', views.crop, name='cropduster-api-crop'),
]
