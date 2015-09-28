from django.utils.functional import cached_property

from cropduster.models import Size, Thumb
from cropduster.standalone.metadata import MetadataImageFile
from cropduster.views import CropDusterIndex
from cropduster.views.utils import FakeQuerySet

from .models import StandaloneImage


class CropDusterStandaloneIndex(CropDusterIndex):

    is_standalone = True

    @cached_property
    def image_file(self):
        (preview_w, preview_h) = self.preview_size
        return MetadataImageFile(self.request.GET.get('image'),
            upload_to=self.upload_to,
            preview_w=preview_w,
            preview_h=preview_h)

    @cached_property
    def db_image(self):
        if not self.image_file:
            return None
        md5 = self.image_file.metadata.get('md5') or self.image_file.metadata.get('DerivedFrom')
        try:
            standalone = StandaloneImage.objects.get(md5=md5)
        except StandaloneImage.DoesNotExist:
            (preview_w, preview_h) = self.preview_size
            standalone = StandaloneImage.objects.get_from_file(self.image_file.name,
                upload_to=self.upload_to, preview_w=preview_w, preview_h=preview_h)
        db_image = standalone.image.related_object
        if not getattr(db_image, 'pk', None):
            raise Exception("Image does not exist in database")
        if not db_image.image and standalone.image.name:
            db_image.image = standalone.image.name
            db_image.save()
            db_image.save_preview(preview_w=self.preview_size[0], preview_h=self.preview_size[1])
        return db_image

    @cached_property
    def max_w(self):
        try:
            max_w = int(self.request.GET.get('max_w')) or None
        except (TypeError, ValueError):
            pass
        else:
            orig_w = getattr(self.orig_image, 'width', None) or 0
            if not orig_w or max_w < orig_w:
                return max_w
        return None

    @cached_property
    def sizes(self):
        size = getattr(self.image_file.metadata, 'crop_size', None)
        if not size:
            size = Size('crop', max_w=self.max_w)
        else:
            size.max_w = self.max_w
        return [size]

    @cached_property
    def thumbs(self):
        if getattr(self.image_file.metadata, 'crop_thumb', None):
            thumb = self.image_file.metadata.crop_thumb
        else:
            orig_w, orig_h = self.image_file.dimensions
            thumb = Thumb(name="crop",
                crop_x=0, crop_y=0, crop_w=orig_w, crop_h=orig_h,
                width=orig_w, height=orig_h)

            if orig_w and self.max_w:
                thumb.width = self.max_w
                thumb.height = int(round((orig_h / orig_w) * self.max_w))
        return FakeQuerySet([thumb], Thumb.objects.none())

    @cached_property
    def orig_image(self):
        return self.image_file.get_for_size('original')


index = CropDusterStandaloneIndex.as_view()
