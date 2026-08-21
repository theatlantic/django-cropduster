from django.core.exceptions import ImproperlyConfigured
from django.urls import re_path

import cropduster.views
from cropduster.exceptions import CropDusterConfigurationError
from cropduster.standalone import NOT_INSTALLED_MESSAGE


try:
    from cropduster.standalone.views import index as standalone_index
except ImproperlyConfigured:
    # Keep the route reversible without the optional XMP dependencies. Report
    # the missing extra only when the view is requested.
    def standalone_index(request, *args, **kwargs):
        raise CropDusterConfigurationError(NOT_INSTALLED_MESSAGE)


urlpatterns = [
    re_path(r'^$', cropduster.views.index, name='cropduster-index'),
    re_path(r'^crop/', cropduster.views.crop, name='cropduster-crop'),
    re_path(r'^upload/', cropduster.views.upload, name='cropduster-upload'),
    re_path(r'^standalone/', standalone_index, name='cropduster-standalone'),
]
