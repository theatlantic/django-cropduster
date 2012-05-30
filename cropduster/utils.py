import os
from PIL import Image


def rescale(img, w=0, h=0, crop=True, **kwargs):
    """
    Rescale the given image, optionally cropping it to make sure the result
    image has the specified width and height.
    """

    if w <= 0 and h <= 0:
        raise ValueError("Width and height must be greater than zero")

    if w <= 0:
        w = float(img.size[0] * h) / float(img.size[1])
    if h <= 0:
        h = float(img.size[1] * w) / float(img.size[0])

    max_width = w
    max_height = h

    src_width, src_height = img.size
    src_ratio = float(src_width) / float(src_height)
    dst_width, dst_height = max_width, max_height
    dst_ratio = float(dst_width) / float(dst_height)

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
    image.save(tmp_path, image.format)
    os.rename(tmp_path, path)

    return path


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
