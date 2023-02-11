from ..resizing import Crop
from ..exceptions import CropDusterException


class DummyImage(object):
    def __init__(self, image):
        self.size = [image.width, image.height]


def set_as_auto_crop(thumb, reference_thumb, force=False):
    """
    Sometimes you need to move crop sizes into different crop groups. This
    utility takes a Thumb and a new reference thumb that will become its
    parent.

    This function can be destructive so, by default, it does not re-set the
    parent crop if the new crop box is different than the old crop box.
    """
    dummy_image = DummyImage(thumb.image)
    current_best_fit = Crop(thumb.get_crop_box(), dummy_image).best_fit(thumb.width, thumb.height)
    new_best_fit = Crop(reference_thumb.get_crop_box(), dummy_image).best_fit(thumb.width, thumb.height)

    if current_best_fit.box != new_best_fit.box and not force:
        raise CropDusterException("Current image crop based on '%s' is "
            "different than new image crop based on '%s'." % (thumb.reference_thumb.name, reference_thumb.name))

    if reference_thumb.reference_thumb:
        raise CropDusterException("Reference thumbs cannot have reference thumbs.")

    if not thumb.reference_thumb:
        thumb.crop_w = None
        thumb.crop_h = None
        thumb.crop_x = None
        thumb.crop_y = None
    thumb.reference_thumb = reference_thumb
    thumb.save()


def unset_as_auto_crop(thumb):
    """
    Crop information is normalized on the parent Thumb row so auto-crops do not
    have crop height/width/x/y associated with them.

    This function takes a Thumb as an argument, generates the best_fit from
    its reference_thumb, sets the relevant geometry, and clears the original
    reference_thumb foreign key.
    """
    if not thumb.reference_thumb:
        return

    reference_thumb_box = thumb.reference_thumb.get_crop_box()
    crop = Crop(reference_thumb_box, DummyImage(thumb.image))
    best_fit = crop.best_fit(thumb.width, thumb.height)

    thumb.reference_thumb = None
    thumb.crop_w = best_fit.box.w
    thumb.crop_h = best_fit.box.h
    thumb.crop_x = best_fit.box.x1
    thumb.crop_y = best_fit.box.y1
    thumb.save()
