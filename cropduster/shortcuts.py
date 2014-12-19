import PIL.Image
from django.contrib.contenttypes.models import ContentType

from .fields import CropDusterField
from .models import Image, Crop, Thumb
from .resizing import Box


def crop_instance(instance):
    """
    Auto-generate crops for a model instance.
    """
    fieldnames = [f.name for f in (instance._meta.fields + instance._meta.many_to_many) if isinstance(f, CropDusterField)]
    for fieldname in fieldnames:
        field = getattr(instance, fieldname)
        sizes = field.sizes
        if callable(sizes):
            sizes = sizes()

        original_w = field.width
        original_h = field.height

        obj_ct = ContentType.objects.get_for_model(instance)
        crop_img, _ = Image.objects.get_or_create(content_type=obj_ct, object_id=instance.pk)

        crop_img.width = original_w
        crop_img.height = original_h
        crop_img.image = field.name
        crop_img.save()

        crop_img.thumbs.all().delete()

        new_sizes_map = {(s.width, s.height): s for s in sizes}

        for dimensions, size in new_sizes_map.iteritems():
            box = Box(0, 0, original_w, original_h)

            pil_img = PIL.Image.open(field.path)
            crop_box = Crop(box, pil_img)

            best_fit = size.fit_to_crop(crop_box, original_image=pil_img)
            fit_box = best_fit.box
            crop_thumb = Thumb(**{
                "name": size.name,
                "width": fit_box.w,
                "height": fit_box.h,
                "crop_x": fit_box.x1,
                "crop_y": fit_box.y1,
                "crop_w": fit_box.w,
                "crop_h": fit_box.h,
            })
            new_thumbs = crop_img.save_size(size, crop_thumb, permissive=True)

            for name, thumb in new_thumbs.iteritems():
                crop_img.thumbs.add(thumb)
