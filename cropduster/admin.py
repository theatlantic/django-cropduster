from django.contrib import admin
from cropduster.models import Size, SizeSet
from django.conf import settings

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
			settings.STATIC_URL + "admin/cropduster/js/size_set.js",
		)
		css = {
			"all": (
				settings.STATIC_URL + "admin/cropduster/css/size_set.css",
			)
		}

admin.site.register(SizeSet, SizeSetAdmin)