from django.conf.urls.defaults import patterns, url

from cropduster import views

urlpatterns = patterns('',
	url(r'^_static/(?P<path>.*)$', views.static_media, name='cropduster-static'),
	url(r'^upload/', views.upload, name='cropduster-upload'),
)
