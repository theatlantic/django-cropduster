from django.conf.urls.defaults import patterns, url

from cropduster import views

urlpatterns = patterns('',
	url(r'^_static/(?P<path>.*)$', views.static_media, name='cropduster-static'),
	url(r'^crop/', views.crop, name='cropduster-crop'),
	url(r'^upload/', views.upload, name='cropduster-upload'),
	url(r'^upload_progress/', views.upload_progress, name='cropduster-upload_progress'),
)
