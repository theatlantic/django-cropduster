from django.conf.urls.defaults import patterns, url
import os

urlpatterns = patterns('',
    url(r'^upload/', "cropduster3.views.upload", name='cropduster-upload'),
    url(r'^_static/(?P<path>.*)$', "django.views.static.serve", {
        "document_root": os.path.dirname(__file__) + "/media",
    }, name='cropduster-static'),
)
