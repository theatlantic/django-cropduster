import os
from PIL import Image, ImageFile
from django.conf import settings

# We have to up the max block size for an image when using optimize, or it
# will blow up
ImageFile.MAXBLOCK = 10000000 # ~10mb


def rescale(img, w=0, h=0, crop=True, **kwargs):
    """
    Rescale the given image, optionally cropping it to make sure the result
    image has the specified width and height.
    """
    dst_width, dst_height, dst_ratio = normalize_dimensions(img, (w, h), return_ratio=True)

    src_width, src_height = img.size
    src_ratio = float(src_width) / float(src_height)

    img_format = img.format
    if crop:
        if dst_ratio < src_ratio:
            crop_height = src_height
            crop_width = crop_height * dst_ratio
            x_offset = float(src_width - crop_width) / 2
            y_offset = 0
        else:
            crop_width = src_width
            crop_height = crop_width / dst_ratio
            x_offset = 0
            y_offset = float(src_height - crop_height) / 2

        img = img.crop((
            int(x_offset),
            int(y_offset),
            int(x_offset + crop_width),
            int(y_offset + crop_height),
        ))
    new_img = img.resize((int(dst_width), int(dst_height)), Image.ANTIALIAS)
    new_img.format = img_format

    return new_img


def normalize_dimensions(img, dimensions, return_ratio=False):
    """
    Given a PIL image and a tuple of (width, height), where `width` OR `height`
    are either numeric or NoneType, returns (dst_width, dst_height) where both
    dst_width and dst_height are integers, the None values having been scaled
    based on the image's aspect ratio.
    """
    max_width, max_height = dimensions
    dst_width, dst_height = max_width, max_height
    src_width, src_height = img.size

    if dst_width > 0 and dst_height > 0:
        pass
    elif dst_width <= 0:
        dst_width = float(src_width * max_height) / float(src_height)
    elif dst_height <= 0:
        dst_height = float(src_height * max_width) / float(src_width)
    else:
        raise ValueError("Width and height must be greater than zero")

    if return_ratio:
        dst_ratio = float(dst_width) / float(dst_height)
        return (int(dst_width), int(dst_height), dst_ratio)
    else:
        return (int(dst_width), int(dst_height))    


def create_cropped_image(path=None, x=0, y=0, w=0, h=0):
    if path is None:
        raise ValueError("A path must be specified")
    if w <= 0 or h <= 0:
        raise ValueError("Width and height must be greater than zero")

    img = Image.open(path)
    img.load()
    img_format = img.format
    new_img = img.crop((x, y, x + w, y + h))
    new_img.load()
    new_img.format = img_format
    return new_img


def rescale_signal(sender, instance, created, max_height=None, max_width=None, **kwargs):
    """
    Simplified image resizer meant to work with post-save/pre-save tasks
    """

    max_width = max_width
    max_height = max_height

    if not max_width and not max_height:
        raise ValueError("Either max width or max height must be defined")

    if max_width and max_height:
        raise ValueError("To avoid improper scaling, only define a width or "
                         "a height, not both")

    if instance.image:
        im = Image.open(instance.image.path)

        if max_width:
            height = instance.image.height * max_width / instance.image.width
            size = max_width, height

        if max_height:
            width = instance.image.width * max_height / instance.image.height
            size = width, max_height

        im.thumbnail(size, Image.ANTIALIAS)
        im.save(instance.image.path)


IMAGE_SAVE_PARAMS = {"quality": 85, "optimize": 1}
def save_image(image, path):
    """
    Attempts to save an image to the provided path.  If the
    extension provided is incorrect according to pil, it will
    try to give the correct extension.

    @param image: PIL image to save
    @type  image: PIL image

    @param path: Absolute path to the save location.
    @type  path: /path/to/image

    @returns path to image
    @rtype /path/to/image
    """
    assert os.path.isabs(path)
    dirpath, name = os.path.split(path)
    if not os.path.exists(dirpath):
        os.makedirs(dirpath)

    tmp_path = os.path.join(dirpath, 'tmp.' + name)

    # Since people upload images with garbage extensions,
    # preserve the decoder format.  You will note that we pass
    # the format along anytime we transform an image in 'utils'
    if hasattr(settings, 'CROPDUSTER_TRANSCODE'):
        new_format = settings.CROPDUSTER_TRANSCODE.get(image.format, image.format)
    else:
        new_format = image.format
    image.save(tmp_path, new_format, **IMAGE_SAVE_PARAMS)
    os.rename(tmp_path, path)

    return path, new_format


def copy_image(image):
    """
    Copies an image, preserving format.

    @param image: PIL Image
    @type  image: PIL Image

    @return: Copy of PIL Image
    @rtype: PIL Image
    """
    img_format = image.format
    image = image.copy()
    image.format = img_format
    return image
