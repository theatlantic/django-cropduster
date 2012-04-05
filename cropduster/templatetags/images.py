from coffin import template
from coffin.template.loader import get_template
register = template.Library()
from django.conf import settings
from cropduster.models import Size

CROPDUSTER_CROP_ONLOAD = getattr(settings, 'CROPDUSTER_CROP_ONLOAD', True)
CROPDUSTER_KITTY_MODE = getattr(settings, 'CROPDUSTER_KITTY_MODE', False)


image_sizes = Size.objects.all()
image_size_map = {}
for size in image_sizes:
	image_size_map[(size.size_set_id, size.slug)] = size


@register.object
def get_image(image, size_name="large", template_name="image.html", width=None, height=None, **kwargs):

	if image:
		
		if CROPDUSTER_CROP_ONLOAD:
			import os
			thumb_path = image.thumbnail_path(size_name)
			if not os.path.exists(thumb_path) and os.path.exists(image.image.path):
				try:
					size = image.size_set.size_set.get(slug=size_name)
				except Size.DoesNotExist:
					return ""
				image.create_individual_thumbnail(size)
		
		
		image_url = image.thumbnail_url(size_name)
		if image_url is None or image_url == "":
			return ""
		try:
			image_size = image_size_map[(image.size_set_id,size_name)]
		except KeyError:
			return ""
	
		kwargs["image_url"] = image_url			
		kwargs["width"] = width or image_size.width or ""
		kwargs["height"] = height or image_size.height  or ""
		

		if CROPDUSTER_KITTY_MODE:
			kwargs["image_url"] = "http://placekitten.com/{0}/{1}".format(kwargs["width"], kwargs["height"])

		kwargs["size_name"] = size_name
		kwargs["attribution"] = image.attribution
		kwargs["alt"] = kwargs["alt"] if "alt" in kwargs else image.caption
		kwargs["title"] = kwargs["title"] if "title" in kwargs else kwargs["alt"]

		tpl = get_template("templatetags/" + template_name)
		ctx = template.Context(kwargs)
		return tpl.render(ctx)
	else:
		return ""

	
		
		