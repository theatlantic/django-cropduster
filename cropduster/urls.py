try:
    from django.conf.urls import patterns, url
except ImportError:
    from django.conf.urls.defaults import patterns, url


urlpatterns = patterns('cropduster.views',
    url(r'^$', 'index', name='cropduster-index'),
    url(r'^crop/', 'crop', name='cropduster-crop'),
    url(r'^upload/', 'upload', name='cropduster-upload'),
)
