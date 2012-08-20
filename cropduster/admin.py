from django.contrib import admin
from cropduster.models import Size, SizeSet
from django.conf import settings

ADMIN_MEDIA_PREFIX = getattr(settings, "STANDARD_ADMIN_MEDIA_PREFIX", settings.ADMIN_MEDIA_PREFIX) 

class SizeInline(admin.TabularInline):
	model = Size
	prepopulated_fields = {"slug" : ("name",)}
	
	fieldsets = (
		(None, {
			"fields": (
				"name", 
				"slug", 
				"width", 
				"height",
				"auto_size",
				"size_set", 
				"aspect_ratio",
				"create_on_request",
				"retina",
			)
		}),
	)
	readonly_fields = ("aspect_ratio",)


class SizeSetAdmin(admin.ModelAdmin):
	prepopulated_fields = {"slug" : ("name",)}

	inlines = [
		SizeInline,
	]
	
	class Media:

		js = (
			ADMIN_MEDIA_PREFIX + "cropduster/js/size_set.js",
		)
		css = {
			"all": (
				ADMIN_MEDIA_PREFIX + "cropduster/css/size_set.css",
			)
		}

admin.site.register(SizeSet, SizeSetAdmin)