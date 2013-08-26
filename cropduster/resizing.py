from __future__ import division
import re
import math


__all__ = ('Size', 'Box', 'Crop')


class Size(object):

    parent = None

    def __init__(self, name, label=None, w=None, h=None, retina=False, auto=None, min_w=None, min_h=None):
        from django.core.exceptions import ImproperlyConfigured

        self.min_w = max(w, min_w)
        self.min_h = max(h, min_h)

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

    def __unicode__(self):
        name = u'Size %s (%s):' % (self.label, self.name)
        if self.auto:
            name = u'%s[auto]' % name
        if self.retina:
            name = u'%s[@2x]' % name
        kw = []
        for k in ['w', 'h', 'min_w', 'min_h']:
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

    def fit_to_crop(self, crop, original_image=None):
        from cropduster.models import Thumb

        if isinstance(crop, Thumb):
            crop_box = crop.get_crop_box()
            crop = Crop(crop_box, original_image)

        best_fit_kwargs = {
            'min_w': self.min_w or self.width,
            'min_h': self.min_h or self.height,
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
            'retina': self.retina,
            'auto': None,
            'label': self.label,
            '__type__': 'cropduster.resizing.Size',
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
        y = (self.y1 + self.y2) / 2;
        return (x, y)

    @property
    def size(self):
        return (self.w, self.h)

    def as_tuple(self):
        return (self.x1, self.y1, self.x2, self.y2)


class Crop(object):

    def __init__(self, box, image):
        self.box = box
        self.image = image
        self.bounds = Box(0, 0, *image.size)

    def create_image(self, width=None, height=None):
        import PIL.Image
        from cropduster.exceptions import CropDusterResizeException

        image = self.image.copy()
        image.load()
        new_image = image.crop(self.box.as_tuple())
        new_image.load()
        new_w, new_h = new_image.size
        if new_w < width or new_h < height:
            raise CropDusterResizeException(
                u"Crop box (%dx%d) is too small for resize to (%dx%d)" % (new_w, new_h, width, height))
        elif new_w > width or new_h > height:
            new_image = new_image.resize((width, height), PIL.Image.ANTIALIAS)
        return new_image

    def best_fit(self, w=None, h=None, min_w=None, min_h=None):
        if w and h:
            aspect_ratio = w / h
        else:
            aspect_ratio = self.box.aspect_ratio

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
            w = (x2 - x1) * (scale_y / scale_x)
            dw = initial_fit.w - w
            x1 += (dw / 2)
            x2 = x1 + w
        elif scale_x < scale_y:
            h = (y2 - y1) * (scale_x / scale_y)
            dh = initial_fit.h - h
            y1 += (dh / 2)
            y2 = y1 + h

        w = int(round(w))
        h = int(round(h))

        x1 = max(int(round(x1)), 0)
        y1 = max(int(round(y1)), 0)
        x2 = min(int(round(x2)), self.bounds.x2, x1 + w)
        y2 = min(int(round(y2)), self.bounds.y2, y1 + h)

        return Crop(Box(x1, y1, x2, y2), self.image)
