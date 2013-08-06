import os
import copy
from itertools import count
from collections import namedtuple

from PIL import Image as pil

from django.forms import ModelForm, ValidationError, HiddenInput
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import render_to_response
from django.template import RequestContext

from .models import Image, Crop, Size, SizeSet, ImageMetadata, ImageRegistry


BROWSER_WIDTH = 800


class MetadataForm(ModelForm):

    class Meta:
        model = ImageMetadata


# Create the form class.
class ImageForm(ModelForm):

    class Meta:
        model = Image
        fields = ('image', 'metadata')

        widgets = {
            'metadata': HiddenInput()
        }

    def clean_image(self):
        image = self.cleaned_data.get('image')

        if not image:
            return image

        if os.path.splitext(image.name)[1] == '':
            raise ValidationError("Please make sure images have file "
                                  "extensions before uploading")

        try:
            pil_image = pil.open(image)
        except IOError:
            raise ValidationError("Unable to open image file")
        except Exception:
            # We need to log here!
            raise ValidationError("Unknown error processing image")

        size_set = self.data.get('size_set')
        if not size_set:
            raise ValidationError("No size set found!")
        else:
            img_size = pil_image.size
            for size in size_set.size_set.filter(auto_crop=False):
                if (img_size[0] < size.width or img_size[1] < size.height):
                    (w, h) = img_size[0:2]
                    raise ValidationError((
                        "Uploaded image (%s x %s) is smaller"
                        " than a required thumbnail size: %s"
                      ) % (w, h, size))

        return image


class CropForm(ModelForm):

    class Meta:
        model = Crop

    def _clean(self):
        if not('crop_x' in self.data and 'crop_y' in self.data):
            self._errors.clear()
            raise ValidationError("Missing crop values")

        if int(self.data['crop_x']) < 0 or int(self.data['crop_y']) < 0:
            self._errors.clear()
            raise ValidationError("Crop positions must be non-negative")

        if int(self.data['crop_w']) < 1 or int(self.data['crop_h']) < 1:
            self._errors.clear()
            raise ValidationError("Crop must have a height and width of at least one pixel")

        return self.cleaned_data


def get_image(request):
    image_id = request.GET.get('image_id') or request.POST.get('image_id')
    image_hash = request.GET.get('image_hash')
    cls = ImageRegistry.get(image_hash)
    if image_id is not None:
        image = cls.objects.get(id=image_id)
    else:
        image = cls()

    return image


def apply_size_set(image, size_set):
    # Do we already have the image_set?
    if image.size_sets.filter(id=size_set.id).count() == 1:
        sizes = Size.objects.filter(size_set__id=size_set.id)
        der_images = image.derived.filter(size__in=[s.id for s in sizes])
    else:
        der_images = image.add_size_set(size_set)

    images = []
    for i in der_images:
        if not i.id:
            i.save()
        if not i.size.auto_crop:
            images.append(i)

    return images


Dimensions = namedtuple('Dimensions', 'width,height,ar')


def get_inherited_dims(image):
    o = image.original
    return Dimensions(image.size.get_width(),
                      image.size.get_height(),
                      image.size.get_aspect_ratio())


def get_inherited_ar(image):
    return get_inherited_dims(image)[2]


def calc_min_dims(images):
    widths, heights, ars = zip(get_inherited_dims(i) for i in images)
    assert(min(ars) == max(ars))
    return max(widths), max(heights)


def calc_linked_crop(images, prefix):
    dims = [get_inherited_dims(i) for i in images]
    max_dim = max(dims)
    ids = ','.join(str(i.id) for i in images)

    if images[0].crop is not None:
        # Start from the current crop if it exists.
        c = images[0].crop
        crop = Crop(crop_x=c.crop_x,
                    crop_y=c.crop_y,
                    crop_w=c.crop_w,
                    crop_h=c.crop_h)
    else:
        crop = Crop(0, 0, 0, 0)

    return (ids, max_dim,
            CropForm(instance=crop,
                     prefix=prefix))


def get_crops(images):
    """
    Gets the crop objects for the thumbs.  It will group images by aspect ratio
    so the user will only need to create one crop per aspect ratio when
    creating.  However, during edit, each image will be broken out with
    unique crops.

    TODO: Solve the case where we want to edit a crop form.  Right now we are
    assuming that this is a new set of crops.

    @param images: Set of sizes and calculated dimensions.
    @type  images: <(image, (width, height, aspect_ratio)), ...>

    @return:
    @rtype:
    """
    # group sizes by aspect ratio
    crops = []
    counter = count(0)
    for aspect_ratio, imageset in categorize(images, get_inherited_ar).iteritems():
        if aspect_ratio is None:
            # We have an unbound dimension in this case, add them individually
            for img in imageset:
                crops.append(calc_linked_crop([img], `next(counter)`))
        else:
            crops.append(calc_linked_crop(imageset, `next(counter)`))

    return crops


def categorize(iterator, key=None):
    if callable(key):
        iterator = ((key(i), i) for i in iterator)

    d = {}
    for c, i in iterator:
        try:
            d[c].append(i)
        except KeyError:
            d[c] = [i]

    return d


def min_size(size_set):
    """
    Calculates the minimum dimensions from a size_set
    """
    width, height = 0, 0
    for s in size_set.size_set.all():
        w, h, a = s.get_dimensions()
        width = max(width, w)
        height = max(height, h)

    return width, height


def upload_image(request, image_form=None, metadata_form=None):
    size_set = SizeSet.objects.get(id=request.GET['size_set'])
    if image_form is None:
        image = get_image(request)
        image_form = ImageForm(instance=image)
    else:
        image = image_form.instance

    if metadata_form is None:
        metadata_form = MetadataForm(instance=image.metadata)

    m_width, m_height = min_size(size_set)
    context = {
        'image_form': image_form,
        'metadata_form': metadata_form,
        'image': image,
        'size_set': size_set,
        'm_width': m_width,
        'm_height': m_height,
        'next_stage': 'crop_images',
        'current_stage': 'upload',
        'is_popup': True,
    }

    return render_to_response('admin/upload_image.html', context)


def upload_crop_images(request):
    size_set = SizeSet.objects.get(id=request.GET['size_set'])
    image = get_image(request)

    # We need to inject the size set id into the form data,
    # or we can't validate that the image dimensions are big
    # enough.
    post = request.POST.copy()
    post['size_set'] = size_set
    image_form = ImageForm(post, request.FILES, instance=image)
    metadata_form = MetadataForm(post, instance=image.metadata)
    if image_form.is_valid() and metadata_form.is_valid():
        metadata = metadata_form.save()
        image = image_form.save()
        # this works, it's terrible, but it works.
        image.metadata = metadata
        image.save()

        sizes = apply_size_set(image, size_set)

        context = {
            'formset': image_form,
            'browser_width': BROWSER_WIDTH,
            'image_element_id': request.GET['image_element_id'],
            'image': image,
            'sizes': sizes,
            'crops': get_crops(sizes),
            'next_stage': 'apply_sizes',
            'current_stage': 'crop_images',
            'is_popup': True,
        }

        context = RequestContext(request, context)
        return render_to_response('admin/crop_images.html', context)

    else:
        return upload_image(request, image_form, metadata_form)


def get_ids(request, index):
    return (int(i) for i in request.POST['crop_ids_%i' % index].split(','))


def get_crops_from_post(request):
    total_crops = int(request.POST['total_crops'])
    crop_mapping = {}
    for i in xrange(total_crops):
        # Build a crop form
        cf = CropForm(request.POST, prefix=`i`)
        if cf.is_valid():
            for image_id in get_ids(request, i):
                crop_mapping[image_id] = cf.instance
        else:
            # Right now, just blow up
            raise Exception(cf.errors.values())

    return crop_mapping


def update_crop(der_image, crop):
    der_image.set_crop(crop.crop_x, crop.crop_y, crop.crop_w, crop.crop_h).save()
    der_image.crop = der_image.crop


def apply_sizes(request):
    # Get each crop and validate it
    crop_mapping = get_crops_from_post(request)

    # Get the derived images from the original image.
    image = get_image(request)

    # Copy each crop into each image, render, and get the thumbnail.
    thumbs = []
    for der_image in image.derived.all():
        if der_image.id in crop_mapping:
            update_crop(der_image, crop_mapping[der_image.id])

        # Render the thumbnail...
        der_image.render()
        der_image.save()

        # Only show cropped images in the admin.
        if der_image.id in crop_mapping:
            thumbs.append(der_image)

    context = {
        'image': image,
        'image_thumbs': thumbs,
        'image_element_id': request.GET['image_element_id'],
        'is_popup': True,
    }

    context = RequestContext(request, context)
    return render_to_response('admin/complete.html', context)

STAGES = {
    'upload': upload_image,
    'crop_images': upload_crop_images,
    'apply_sizes': apply_sizes,
}


def get_next_stage(request):
    return request.POST.get('next_stage', 'upload')


def dispatch_stage(request):
    stage = get_next_stage(request)
    if stage in STAGES:
        return STAGES[stage](request)

    #Raise error
    return None


@csrf_exempt
def upload(request):
    return dispatch_stage(request)
