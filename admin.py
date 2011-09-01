from django.contrib import admin
from cropduster.models import Size, SizeSet

class SizeAdmin(admin.ModelAdmin):
	prepopulated_fields = {"slug" : ('name',)}
	
	fieldsets = (
		(None, {
			'fields': (
				'name', 
				'slug', 
				'width', 
				'height', 
				'auto_size',
				'size_set', 
				'aspect_ratio',
			)
		}),
	)
	readonly_fields = ('aspect_ratio',)

class SizeSetAdmin(admin.ModelAdmin):
	prepopulated_fields = {"slug" : ('name',)}

admin.site.register(Size, SizeAdmin)
admin.site.register(SizeSet, SizeSetAdmin)