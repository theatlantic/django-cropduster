from django.conf.urls.defaults import patterns, url

urlpatterns = patterns(
    '',
    url(r'^crop/', 'cropduster.views.crop'),
	url(r'^upload/', 'cropduster.views.upload'),
	url(r'^upload_progress/', 'cropduster.views.upload_progress'),
)
