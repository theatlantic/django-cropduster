from django.urls import re_path

import cropduster.views
import cropduster.standalone.views


urlpatterns = [
    re_path(r'^$', cropduster.views.index, name='cropduster-index'),
    re_path(r'^crop/', cropduster.views.crop, name='cropduster-crop'),
    re_path(r'^upload/', cropduster.views.upload, name='cropduster-upload'),
    re_path(r'^standalone/', cropduster.standalone.views.index, name='cropduster-standalone'),
]
