from django.forms import HiddenInput
from coffin.template import Context, loader
from django.core.urlresolvers import reverse
from cropduster.models import SizeSet, Image as CropDusterImage

class AdminCropdusterWidget(HiddenInput):
	def __init__(self, size_set_slug, *args, **kwargs):
		self.size_set = SizeSet.objects.get(slug=size_set_slug)
		super(AdminCropdusterWidget, self).__init__(*args, **kwargs)
	
	def render(self, name, value, attrs=None):
		attrs.setdefault("class", "cropduster")
		
		media_url = reverse("cropduster-static", kwargs={"path":""})
		
		cropduster_url = reverse("cropduster-upload")
	
		input = super(HiddenInput, self).render(name, value, attrs)
		
		try:
			image = CropDusterImage.objects.get(id=value)
		except:
			image = None
		
		
		
		t = loader.get_template("cropduster/inline.html")
		c = Context({
			"image": image,
			"size_set": self.size_set,
			"media_url": media_url,
			"cropduster_url": cropduster_url,
			"input": input,
			"attrs": attrs,
		})
		return t.render(c)