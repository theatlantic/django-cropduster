from django.contrib import admin
from cropduster.models import Size, SizeSet

class SizeAdmin(admin.ModelAdmin):
	pass

class SizeSetAdmin(admin.ModelAdmin):
	pass

admin.site.register(Size, SizeAdmin)
admin.site.register(SizeSet, SizeSetAdmin)