from coffin import template
from coffin.template.loader import get_template
register = template.Library()
from django.conf import settings
from cropduster.models import Size
from os.path import exists

CROPDUSTER_CROP_ONLOAD = getattr(settings, "CROPDUSTER_CROP_ONLOAD", True)
CROPDUSTER_KITTY_MODE = getattr(settings, "CROPDUSTER_KITTY_MODE", False)


# preload a map of image sizes so it doesn"t make a DB call for each templatetag use
IMAGE_SIZE_MAP = {}
for size in Size.objects.all():
	IMAGE_SIZE_MAP[(size.size_set_id, size.slug)] = size


@register.object
def get_image(image, size_name=None, template_name="image.html", **kwargs):
	""" Templatetag to get the HTML for an image from a cropduster image object """

	if image:
		
		if CROPDUSTER_CROP_ONLOAD:
		# If set, will check for thumbnail existence
		# if not there, will create the thumb based on predefiend crop/size settings
		
			thumb_path = image.thumbnail_path(size_name)
			if not exists(thumb_path) and exists(image.image.path):
				try:
					size = image.size_set.size_set.get(slug=size_name)
				except Size.DoesNotExist:
					return ""
				image.create_thumbnail(size, force_crop=True)
		
		image_url = image.thumbnail_url(size_name)
		
		if not image_url:
			return ""
		try:
			image_size = IMAGE_SIZE_MAP[(image.size_set_id, size_name)]
		except KeyError:
			return ""
	
		# Set all the args that get passed to the template
		
		kwargs["image_url"] = image_url
			
		kwargs["width"] = image_size.width if hasattr(image_size, "width") else ""
		
		kwargs["height"] = image_size.height if hasattr(image_size, "height") else ""
		
		
		if CROPDUSTER_KITTY_MODE:
			kwargs["image_url"] = "http://placekitten.com/%s/%s" % (kwargs["width"], kwargs["height"])
		
		kwargs["size_name"] = size_name
		
		kwargs["attribution"] = image.attribution
		
		if hasattr(image, "caption"): kwargs["alt"] = image.caption 
		
		if "title" not in kwargs: kwargs["title"] = kwargs["alt"] 

		tmpl = get_template("templatetags/" + template_name)
		context = template.Context(kwargs)
		return tmpl.render(context)
	else:
		return ""

	
		
		