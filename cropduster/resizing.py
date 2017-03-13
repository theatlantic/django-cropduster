from __future__ import division

import os
import re
import math
import hashlib
import tempfile

import PIL.Image
from PIL.ImageFile import ImageFile
from django.db.models.fields.files import FieldFile
from django.core.exceptions import ImproperlyConfigured
from django.utils import six
from django.utils.six.moves import filter

from .settings import CROPDUSTER_RETAIN_METADATA


if hasattr(six.moves.builtins, 'file'):
    BUILTIN_FILE_TYPE = file
else:
    from io import IOBase as BUILTIN_FILE_TYPE


__all__ = ('Size', 'Box', 'Crop')


INFINITY = float('inf')


class Size(object):

    parent = None

    def __init__(self, name, label=None, w=None, h=None, retina=False, auto=None, min_w=None, min_h=None,
            max_w=None, max_h=None, required=True):

        self.min_w = max(w or 1, min_w or 1) or 1
        self.min_h = max(h or 1, min_h or 1) or 1
        self.max_w = max_w
        self.max_h = max_h

        if auto is not None:
            try:
                if not all([isinstance(sz, Size) for sz in auto]):
                    raise TypeError()
            except TypeError:
                raise Exception("kwarg `auto` must be a list of Size objects")
            else:
                for auto_size in auto:
                    auto_size.parent = self
                    if auto_size.auto:
                        raise ImproperlyConfigured("The `auto` kwarg cannot be used recursively")
        self.name = name
        self.auto = auto
        self.retina = retina
        self.width = w
        self.height = h
        self.label = label or u' '.join(filter(None, re.split(r'[_\-]', name))).title()
        self.required = required

        self.min_aspect = (self.w / self.h) if (self.w and self.h) else 0
        self.max_aspect = self.min_aspect or INFINITY

        if self.w and self.min_h > 1:
            self.max_aspect = min(self.max_aspect, self.w / self.min_h)

        if self.w and self.max_h:
            self.min_aspect = max(self.min_aspect, self.w / self.max_h)

        if self.h and self.min_w > 1:
            self.min_aspect = max(self.min_aspect, self.min_w / self.h)

        if self.h and self.max_w:
            self.max_aspect = min(self.max_aspect, self.max_w / self.h)

    def __unicode__(self):
        name = u'Size %s (%s):' % (self.label, self.name)
        if self.auto:
            name = u'%s[auto]' % name
        if self.retina:
            name = u'%s[@2x]' % name
        kw = []
        for k in ['w', 'h', 'min_w', 'min_h', 'max_w', 'max_h']:
            v = getattr(self, k, None)
            if v:
                kw.append(u'%s=%s' % (k, v))
        if len(kw):
            name += u'(%s)' % (u', '.join(kw))
        return name

    @property
    def w(self):
        return self.width

    @property
    def h(self):
        return self.height

    @property
    def is_auto(self):
        return self.parent is not None

    @staticmethod
    def flatten(sizes):
        for size in sizes:
            yield size
            if size.auto:
                for auto_size in size.auto:
                    yield auto_size

    @property
    def aspect_ratio(self):
        if not self.width or not self.height:
            return None
        return self.width / self.height

    def fit_image(self, original_image):
        orig_w, orig_h = original_image.size
        crop = Crop(Box(0, 0, orig_w, orig_h), original_image)
        return self.fit_to_crop(crop, original_image=original_image)

    def fit_to_crop(self, crop, original_image=None):
        from cropduster.models import Thumb

        if isinstance(crop, Thumb):
            crop_box = crop.get_crop_box()
            crop = Crop(crop_box, original_image)

        best_fit_kwargs = {
            'min_w': self.min_w or self.width,
            'min_h': self.min_h or self.height,
            'max_w': self.max_w,
            'max_h': self.max_h,
            'min_aspect': self.min_aspect,
            'max_aspect': self.max_aspect,
        }
        if self.width and self.height:
            best_fit_kwargs.update({'w': self.width, 'h': self.height})
        return crop.best_fit(**best_fit_kwargs)

    def __serialize__(self):
        data = {
            'name': self.name,
            'w': self.w,
            'h': self.h,
            'min_w': self.min_w,
            'min_h': self.min_h,
            'max_w': self.max_w,
            'max_h': self.max_h,
            'retina': 1 if self.retina else 0,
            'label': self.label,
            'required': self.required,
            '__type__': 'Size',
        }
        if self.auto:
            data['auto'] = [sz.__serialize__() for sz in self.auto]

        return data


class Box(object):

    def __init__(self, x1, y1, x2, y2):
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2

    @property
    def w(self):
        return self.x2 - self.x1

    @property
    def h(self):
        return self.y2 - self.y1

    @property
    def aspect_ratio(self):
        try:
            return self.w / self.h
        except:
            return 1

    @property
    def midpoint(self):
        x = (self.x1 + self.x2) / 2
        y = (self.y1 + self.y2) / 2
        return (x, y)

    @property
    def size(self):
        return (self.w, self.h)

    def as_tuple(self):
        return (self.x1, self.y1, self.x2, self.y2)

    def __eq__(self, other):
        return (isinstance(other, self.__class__) and self.as_tuple() == other.as_tuple())

    def __ne__(self, other):
        return not self.__eq__(other)


class Crop(object):

    def __init__(self, box, image):
        if isinstance(image, six.string_types):
            image = PIL.Image.open(image)

        self.box = box
        self.image = image
        self.bounds = Box(0, 0, *image.size)

    def create_image(self, output_filename, width, height):
        from cropduster.utils import process_image, get_image_extension

        temp_file = tempfile.NamedTemporaryFile(suffix=get_image_extension(self.image), delete=False)
        temp_filename = temp_file.name
        with open(self.image.filename, mode='rb') as f:
            temp_file.write(f.read())
        temp_file.seek(0)
        image = PIL.Image.open(temp_filename)

        crop_args = self.box.as_tuple()

        def crop_and_resize_callback(im):
            from cropduster.utils import smart_resize
            im = im.crop(crop_args)
            return smart_resize(im, final_w=width, final_h=height)

        new_image = process_image(image, output_filename, crop_and_resize_callback)
        new_image.crop = self
        temp_file.close()
        os.unlink(temp_filename)
        return new_image

    def best_fit(self, w=None, h=None, min_w=None, min_h=None, max_w=None, max_h=None, min_aspect=None, max_aspect=None):
        if w and h:
            aspect_ratio = w / h
        else:
            aspect_ratio = self.box.aspect_ratio

        if min_aspect and aspect_ratio < min_aspect:
            aspect_ratio = min_aspect
        elif max_aspect and aspect_ratio > max_aspect:
            aspect_ratio = max_aspect

        scale = math.sqrt(aspect_ratio / self.box.aspect_ratio)

        w = self.box.w * scale
        h = w / aspect_ratio

        # Scale our initial width and height based on the min_w and min_h
        min_scales = []
        if min_w and min_w > w:
            min_scales.append(min_w / w)
        if min_h and min_h > h:
            min_scales.append(min_h / h)
        if min_scales:
            min_scale = max(min_scales)
            w = w * min_scale
            h = h * min_scale

        midx, midy = self.box.midpoint
        x1 = midx - (w / 2)
        y1 = midy - (h / 2)
        x2 = x1 + w
        y2 = y1 + h

        initial_fit = Box(x1, y1, x2, y2)

        # scale and translate to fit inside image bounds,
        # based on initial best fit.

        scale_x = scale_y = 1

        if x1 < 0:
            x2 += (-1 * x1)
            x1 = 0
        if x2 > self.bounds.w:
            x1 = max(self.bounds.w - initial_fit.w, 0)
            x2 = self.bounds.w
            scale_x = (x2 - x1) / initial_fit.w

        if y1 < 0:
            y2 += (-1 * y1)
            y1 = 0
        if y2 > self.bounds.h:
            y1 = max(self.bounds.h - initial_fit.h, 0)
            y2 = self.bounds.h
            scale_y = (y2 - y1) / initial_fit.h

        if scale_y < scale_x:
            # scale down the width to maintain aspect ratio
            w = (x2 - x1) * (scale_y / scale_x)
            # unless the scaled width would drop below the min_w
            if w < min_w:
                w = min_w
            dw = initial_fit.w - w
            x1 += (dw / 2)
            x2 = x1 + w
        elif scale_x <= scale_y:
            # scale down the height to maintain aspect ratio
            h = (y2 - y1) * (scale_x / scale_y)
            # unless the scaled height would drop below the min_h
            if h < min_h:
                h = min_h
            dh = initial_fit.h - h
            y1 += (dh / 2)
            y2 = y1 + h

        w = int(round(w))
        h = int(round(h))

        x1 = max(int(round(x1)), 0)
        y1 = max(int(round(y1)), 0)
        x2 = min(int(round(x2)), self.bounds.x2, x1 + w)
        y2 = min(int(round(y2)), self.bounds.y2, y1 + h)

        # Fix off-by-one rounding errors
        if (x2 - x1 == w - 1):
            if x2 < self.bounds.x2:
                x2 += 1
            elif x1 > self.bounds.x1:
                x1 -= 1
        if (y2 - y1 == h - 1):
            if y2 < self.bounds.y2:
                y2 += 1
            elif y1 > self.bounds.y1:
                y1 -= 1

        return Crop(Box(x1, y1, x2, y2), self.image)

    def add_xmp_to_crop(self, cropped_image, size, original_image=None):
        try:
            from cropduster.standalone.metadata import libxmp, file_format_supported
        except ImproperlyConfigured:
            libxmp = None

        if not libxmp:
            return

        from cropduster.models import Image, Thumb

        def get_image_path(img):
            if isinstance(img, ImageFile):
                path = img.filename
            elif isinstance(img, BUILTIN_FILE_TYPE):
                path = img.name
            elif isinstance(img, FieldFile):
                path = img.path
            elif isinstance(img, Thumb):
                image = img.image
                if not img:
                    return None
                path = image.get_path(img.name)
            elif isinstance(img, Image):
                path = img.get_path('original')
            elif isinstance(img, six.string_types):
                path = img
            else:
                path = None
            return path

        image_path = get_image_path(cropped_image)

        if not image_path:
            return

        xmp_file = libxmp.XMPFiles(file_path=image_path, open_forupdate=True)

        original_metadata = None
        if original_image and CROPDUSTER_RETAIN_METADATA:
            original_image_path = get_image_path(original_image)
            if original_image_path:
                try:
                    original_xmp_file = libxmp.XMPFiles(file_path=original_image_path)
                    original_metadata = original_xmp_file.get_xmp()
                except:
                    pass

        xmp_meta = self.generate_xmp(size, original_metadata=original_metadata)

        if not xmp_file.can_put_xmp(xmp_meta):
            if not file_format_supported(image_path):
                raise Exception("Image format of %s does not allow metadata" % (
                        os.path.basename(image_path)))
            else:
                raise Exception("Could not add metadata to image %s" % (
                        os.path.basename(image_path)))

        xmp_file.put_xmp(xmp_meta)
        xmp_file.close_file()

    def generate_xmp(self, size, original_metadata=None):
        from cropduster.standalone.metadata import libxmp
        from cropduster.utils import json

        NS_MWG_RS = "http://www.metadataworkinggroup.com/schemas/regions/"
        NS_XMPMM = "http://ns.adobe.com/xap/1.0/mm/"
        NS_CROP = "http://ns.thealtantic.com/cropduster/1.0/"

        md5 = hashlib.md5()
        with open(self.image.filename, mode='rb') as f:
            md5.update(f.read())
        digest = md5.hexdigest()

        md = original_metadata or libxmp.XMPMeta()
        md.register_namespace(NS_XMPMM, 'xmpMM')
        md.register_namespace(NS_MWG_RS, 'mwg-rs')
        md.register_namespace('http://ns.adobe.com/xap/1.0/sType/Dimensions#', 'stDim')
        md.register_namespace('http://ns.adobe.com/xmp/sType/Area#', 'stArea')
        md.register_namespace(NS_CROP, 'crop')
        md.set_property(NS_CROP, 'crop:size/stDim:w', '%s' % (size.width or ''))
        md.set_property(NS_CROP, 'crop:size/stDim:h', '%s' % (size.height or ''))
        md.set_property(NS_CROP, 'crop:size/crop:json', json.dumps(size))
        md.set_property(NS_CROP, 'crop:md5', digest.upper())
        md.set_property(NS_MWG_RS, 'mwg-rs:Regions/mwg-rs:AppliedToDimensions', '', prop_value_is_struct=True)
        md.set_property(NS_MWG_RS, 'mwg-rs:Regions/mwg-rs:AppliedToDimensions/stDim:w', six.text_type(self.image.size[0]))
        md.set_property(NS_MWG_RS, 'mwg-rs:Regions/mwg-rs:AppliedToDimensions/stDim:h', six.text_type(self.image.size[1]))
        md.set_property(NS_MWG_RS, 'mwg-rs:Regions/mwg-rs:RegionList', '', prop_value_is_array=True)
        md.set_property(NS_MWG_RS, 'mwg-rs:Regions/mwg-rs:RegionList[1]/mwg-rs:Name', 'Crop')
        md.set_property(NS_MWG_RS, 'mwg-rs:Regions/mwg-rs:RegionList[1]/mwg-rs:Area', '', prop_value_is_struct=True)
        md.set_property(NS_MWG_RS, 'mwg-rs:Regions/mwg-rs:RegionList[1]/mwg-rs:Area/stArea:unit', "normalized")
        md.set_property(NS_MWG_RS, 'mwg-rs:Regions/mwg-rs:RegionList[1]/mwg-rs:Area/stArea:w', "%.5f" % (self.box.w / self.bounds.w))
        md.set_property(NS_MWG_RS, 'mwg-rs:Regions/mwg-rs:RegionList[1]/mwg-rs:Area/stArea:h', "%.5f" % (self.box.h / self.bounds.h))
        md.set_property(NS_MWG_RS, 'mwg-rs:Regions/mwg-rs:RegionList[1]/mwg-rs:Area/stArea:x', "%.5f" % (self.box.x1 / self.bounds.w))
        md.set_property(NS_MWG_RS, 'mwg-rs:Regions/mwg-rs:RegionList[1]/mwg-rs:Area/stArea:y', "%.5f" % (self.box.y1 / self.bounds.h))
        return md
