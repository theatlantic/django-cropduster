from django.forms import HiddenInput
from coffin.template import Context, loader
from django.core.urlresolvers import reverse
from cropduster.models import SizeSet, Image as CropDusterImage, ImageRegistry
from django.contrib.contenttypes.models import ContentType


class AdminCropdusterWidget(HiddenInput):

    def __init__(self, model, field, size_set_slug, template="admin/inline.html", *args, **kwargs):
        try:
            self.size_set = SizeSet.objects.get(slug=size_set_slug)
        except SizeSet.DoesNotExist:
            # Throw the error during rendering.
            self.size_set = None
            self.size_set_slug = size_set_slug

        self.register_image(model, field)
        self.template = template
        super(AdminCropdusterWidget, self).__init__(*args, **kwargs)
        self.is_hidden = False

    def register_image(self, model, field_name):
        model_id = ContentType.objects.get_for_model(model)
        field = model._meta.get_field_by_name(field_name)[0]
        image = field.rel.to

        self.image_hash = ImageRegistry.add(model_id, field_name, image)

    def render(self, name, value, attrs=None):
        if self.size_set is None:
            raise SizeSet.DoesNotExist("SizeSet '%s' missing from database" % self.size_set_slug)

        attrs.setdefault("class", "cropduster")
        media_url = reverse("cropduster-static", kwargs={"path": ""})
        cropduster_url = reverse("cropduster-upload")

        input = super(HiddenInput, self).render(name, value, attrs)

        if not value:
            image = None
        else:
            try:
                image = CropDusterImage.objects.get(id=value)
            except CropDusterImage.DoesNotExist:
                image = None

        t = loader.get_template(self.template)
        c = Context({
            "image": image,
            "image_hash": self.image_hash,
            "size_set": self.size_set,
            "media_url": media_url,
            "cropduster_url": cropduster_url,
            "input": input,
            "attrs": attrs,
        })
        return t.render(c)
