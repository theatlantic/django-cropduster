try:
    from django.conf.urls import patterns, url
except ImportError:
    from django.conf.urls.defaults import patterns, url


urlpatterns = patterns('',
    url(r'^$', 'cropduster.views.index', name='cropduster-index'),
    url(r'^crop/', 'cropduster.views.crop', name='cropduster-crop'),
    url(r'^upload/', 'cropduster.views.upload', name='cropduster-upload'),
    url(r'^standalone/', 'cropduster.standalone.views.index', name='cropduster-standalone'),
)
