from django.forms import HiddenInput, Media
from django.template import Context, loader
from django.core.urlresolvers import reverse
from django.contrib.contenttypes.models import ContentType

from .models import SizeSet, Image as CropDusterImage, ImageRegistry


class AdminCropdusterWidget(HiddenInput):

    ctx_overrides = None

    def __init__(self, model, field, size_set_slug, template="admin/inline.html", attrs=None, *args, **ctx_overrides):
        try:
            self.size_set = SizeSet.objects.get(slug=size_set_slug)
        except SizeSet.DoesNotExist:
            # Throw the error during rendering.
            self.size_set = None
            self.size_set_slug = size_set_slug

        self.register_image(model, field)
        self.template = template
        super(AdminCropdusterWidget, self).__init__(attrs)
        self.is_hidden = False
        self.ctx_overrides = ctx_overrides

    def _media(self):
        base = getattr(super(AdminCropdusterWidget, self), 'media', None)
        media = Media(base) if base else Media()

        media_url = reverse("cropduster-static", kwargs={"path": ""})

        media.add_js([media_url + 'js/admin.cropduster.js',])
        media.add_css({
            'all': (
                media_url + 'css/admin.cropduster.css',
            ),})
        return media

    media = property(_media)

    def register_image(self, model, field_name):
        model_id = ContentType.objects.get_for_model(model)
        field = model._meta.get_field_by_name(field_name)[0]
        image = field.rel.to
        self._image_field = image

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
                image = self._image_field.objects.get(id=value)
            except CropDusterImage.DoesNotExist:
                image = None

        if image:
            filter_kwargs = {
                'size__size_set': self.size_set,
                'size__auto_crop': False,
            }
            filter_kwargs.update(self.ctx_overrides.pop('derived_filter_kwargs', {}))
            manual = image.derived.filter(**filter_kwargs)
        else:
            manual = None

        t = loader.get_template(self.template)
        ctx = {
            "image": image,
            "image_hash": self.image_hash,
            "size_set": self.size_set,
            "media_url": media_url,
            "cropduster_url": cropduster_url,
            "input": input,
            "attrs": attrs,
            "show_original": True,
            "manual": manual,
            "has_manual": image and len(manual) > 0,
        }
        ctx.update(self.ctx_overrides)

        return t.render(Context(ctx))
