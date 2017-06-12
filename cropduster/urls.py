try:
    from django.conf.urls import url
except ImportError:
    from django.conf.urls.defaults import url

import cropduster.views
import cropduster.standalone.views


urlpatterns = [
    url(r'^$', cropduster.views.index, name='cropduster-index'),
    url(r'^crop/', cropduster.views.crop, name='cropduster-crop'),
    url(r'^upload/', cropduster.views.upload, name='cropduster-upload'),
    url(r'^standalone/', cropduster.standalone.views.index, name='cropduster-standalone'),
]
