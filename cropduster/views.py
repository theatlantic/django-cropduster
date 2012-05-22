import os
import copy

from django.http import HttpResponse, Http404
from django.shortcuts import render_to_response
from django.template import RequestContext
from django.forms import TextInput
from django.forms.widgets import Select
from django.views.decorators.csrf import csrf_exempt

from cropduster.models import Image as CropDusterImage, Crop, Size, SizeSet, ImageMetadata
from cropduster.settings import CROPDUSTER_MEDIA_ROOT

from PIL import Image as pil


from django.forms import ModelForm, ValidationError

BROWSER_WIDTH = 800

class MetadataForm(ModelForm):
    class Meta:
        model = ImageMetadata

# Create the form class.
class ImageForm(ModelForm):
    class Meta:
        model = CropDusterImage
        fields = ('image',)

    def clean_image(self):
        image = self.cleaned_data.get("image")
    
        if not image: 
            return image

        if os.path.splitext(image.name)[1] == '':
            raise ValidationError("Please make sure images have file "\
                                  "extensions before uploading")
    
        try:
            pil_image = pil.open(image)
        except IOError:
            raise ValidationError("Unable to open image file")
        except Exception:
            # We need to log here!
            raise ValidationError("Unknown error processing image")
            
        size_set = self.data.get("size_set")
        if size_set:
            img_size = pil_image.size
            for size in size_set.size_set.filter(auto_crop=False):
                if (img_size[0] < size.width or img_size[1] < size.height):

                    raise ValidationError("Uploaded image (%s x %s) is "\
                        "smaller than a required thumbnail size: %s" \
                            % (img_size[0], img_size[1], size)
                    )
        else:
            raise ValidationError("No size set found!")

        return image

class CropForm(ModelForm):
    class Meta:
        model = Crop        

    def _clean(self):
        if not("crop_x" in self.data and "crop_y" in self.data):
            self._errors.clear()
            raise ValidationError("Missing crop values")
            
        if int(self.data["crop_x"]) < 0 or int(self.data["crop_y"]) < 0:
            self._errors.clear()
            raise ValidationError("Crop positions must be non-negative")
        
        return self.cleaned_data
    
def get_image(request):
    image_id = request.GET.get('image_id') or request.POST.get('image_id')
    if image_id is not None:
        image = CropDusterImage.objects.get(id=image_id)
    else:
        image = CropDusterImage()

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

def get_inherited_dims(image):
    o = image.original
    return image.size.calc_dimensions(o.width, o.height)

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
    return (ids, max_dim[2], 
            CropForm(instance=Crop(crop_x=0,
                                   crop_y=0,
                                   crop_w=max_dim[0],
                                   crop_h=max_dim[1]),
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
    for i, (aspect_ratio, imageset) in enumerate(categorize(images, get_inherited_ar).iteritems()):
        crops.append( calc_linked_crop(imageset, `i`))

    return crops

def categorize(iterator, key=None):
    if callable(key):
        iterator = ((key(i),i) for i in iterator)

    d = {}
    for c, i in iterator:
        try:
            d[c].append(i)
        except KeyError:
            d[c] = [i]

    return d

def upload_image(request):
    size_set = SizeSet.objects.get(id=request.GET["size_set"])
    image = get_image(request)

    image_form = ImageForm(instance=image)
    metadata_form = MetadataForm()
    context = {'formset': image_form,
               'metadata_form': metadata_form,
               'image': image,
               'size_set': size_set,
               'next_stage': 'crop_images',
               'current_stage': 'upload'}
    
    return render_to_response("admin/upload_image.html", context)

def upload_crop_images(request):
    size_set = SizeSet.objects.get(id=request.GET['size_set'])
    image = get_image(request)

    # We need to inject the size set id into the form data,
    # or we can't validate that the image dimensions are big
    # enough.
    post = request.POST.copy()
    post['size_set'] = size_set
    formset = ImageForm(post, request.FILES, instance=image)
    if formset.is_valid():
        image = formset.save()
        sizes = apply_size_set(image, size_set)
        context = {'formset': formset,
            "browser_width": BROWSER_WIDTH,
            "image_element_id": request.GET['image_element_id'],
            'image': image,
            "sizes": sizes,
            "crops": get_crops(sizes),
            "next_stage": "apply_sizes",
            "current_stage": "crop_images"
        }

        context = RequestContext(request, context)
        return render_to_response("admin/crop_images.html", context)

    else:
        errors = formset.errors.values()[0]
        context = {
            "errors": errors,
            "formset": formset,
            "image_element_id": request.GET['image_element_id'],
        }

    context = RequestContext(request, context)

    return render_to_response("admin/upload.html", context)

def get_ids(request, index):
    return (int(i) for i in request.POST['crop_ids_%i'%index].split(','))

def get_crops_from_post(request):
    total_crops = int(request.POST['total_crops'])
    crop_mapping = {}
    for i in xrange(total_crops):
        # Build a crop form
        cf = CropForm(request.POST, prefix=`i`)
        if cf.is_valid():
            for image_id in get_ids(request, i):
                crop_mapping[image_id] = copy.copy(cf.instance)
        else:
            # Right now, just blow up
            raise Exception(cf.errors.values())
    return crop_mapping

def apply_sizes(request):
    # Get each crop and validate it
    crop_mapping = get_crops_from_post(request)

    # Get the derived images from the original image.
    image = get_image(request)

    # Copy each crop into each image, render, and get the thumbnail.
    thumbs = []
    for der_image in image.derived.filter(id__in=crop_mapping.keys()):
        der_image.crop = crop_mapping[der_image.id]
        der_image.crop.save()

        # Render the thumbnail...
        der_image.render()
        der_image.save()
        thumbs.append(der_image.image.url)

    context = {
        "image": image,
        "image_thumbs": thumbs,
        "image_element_id" : request.GET["image_element_id"]
    }
    
    context = RequestContext(request, context)
    return render_to_response("admin/complete.html", context)

    # redirect to completed
    raise Exception(request.POST)

STAGES = {
    'upload': upload_image,
    'crop_images': upload_crop_images,
    'apply_sizes': apply_sizes
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
    
    # Initial Get
    if request.method == 'GET' and not request.FILES:
        image_form = ImageForm(instance=image)
        metadata_form = MetadataForm()
        context = {'formset': image_form,
                   'metadata_form': metadata_form,
                   'image': image,
                   'size_set': size_set}
        
        return render_to_response("admin/upload_image.html", context)

    # We've uploaded an image.
    elif request.method == 'POST' and request.FILES:
        # We need to inject the size set id into the form data,
        # or we can't validate that the image dimensions are big
        # enough.
        post = request.POST.copy()
        post['size_set'] = size_set
        formset = ImageForm(post, request.FILES, instance=image)
        if formset.is_valid():
            image = formset.save()
            sizes = apply_sizes(image, size_set)
            context = {'formset': formset,
                "browser_width": BROWSER_WIDTH,
                "image_element_id": request.GET['image_element_id'],
                'image': image,
                "sizes": sizes,
                "crops": get_crops(sizes)
            }
        else:
            errors = formset.errors.values()[0]
            context = {
                "errors": errors,
                "formset": formset,
                "image_element_id": request.GET['image_element_id']
            }

        context = RequestContext(request, context)

        return render_to_response("admin/upload.html", context)

    raise Exception(request.FILES)
    
    if request.method == "POST":
        if request.FILES:
            # Process uploaded image form
            formset = ImageForm(request.POST, request.FILES, instance=image)
            
            if formset.is_valid():
                image = formset.save()
                crop.image = image
                crop_formset = CropForm(instance=crop)
            else:
                # Invalid upload return form
                errors = formset.errors.values()[0]
                context = {
                    "aspect_ratio_id": 0,
                    "errors": errors,
                    "formset": formset,
                    "image_element_id" : request.GET["image_element_id"]
                }
            
                context = RequestContext(request, context)
                
                return render_to_response("admin/upload.html", context)
        else:
                    
            #If its the first frame, get the image formset and save it (for attribution)
            
            if aspect_ratio_id ==0:
                formset = ImageForm(request.POST, instance=image)
                if formset.is_valid():
                    formset.save()
            else:
                formset = ImageForm(instance=image)
                
            # If there's no cropping to be done, then just complete the process
            if size.id:
                
                # Lets save the crop
                request.POST['size'] = size.id
                request.POST['image'] = image.id
                crop_formset = CropForm(request.POST, instance=crop)
                
                if crop_formset.is_valid():
                    crop = crop_formset.save()
                    
                    #Now get the next crop if it exists
                    aspect_ratio_id = aspect_ratio_id + 1
                    size = Size.objects.get_size_by_ratio(size_set, aspect_ratio_id)
                    
                    # If there's another crop
                    if size:
                        try:
                            crop = Crop.objects.get(image=image.id, size=size.id)
                            crop_formset = CropForm(instance=crop)
                        except Crop.DoesNotExist:
                            crop = Crop()
                            crop.crop_w = size.width
                            crop.crop_h = size.height
                            crop.crop_x = 0
                            crop.crop_y = 0
                            crop.size = size
                            crop_formset = CropForm()
            
    # Nothing being posted, get the image and form if they exist
    else:
        formset = ImageForm(instance=CropDusterImage())
        
    # If theres more cropping to be done or its the first frame,
    # show the upload/crop form
    size = Size()
    if (size and size.id) or request.method != "POST":        
        
        crop_w = size.width or crop.crop_w
        crop_h = size.height or crop.crop_h
        
        # Combine errors from both forms, eliminate duplicates
        errors = dict(crop_formset.errors)
        errors.update(formset.errors)
        all_errors = []
        for error in  errors.items():
            all_errors.append(u"%s: %s" % (error[0].capitalize(), error[1].as_text()))
        
        context = {
            "aspect_ratio": size.aspect_ratio,
            "aspect_ratio_id": aspect_ratio_id,    
            "browser_width": BROWSER_WIDTH,
            "crop_formset": crop_formset,
            "crop_w" : crop_w,
            "crop_h" : crop_h,
            "crop_x" : crop.crop_x or 0,
            "crop_y" : crop.crop_y or 0,
            "errors" : all_errors,
            "formset": formset,
            "image": image,
            "image_element_id" : request.GET["image_element_id"],
            "image_exists": image.image and os.path.exists(image.image.path),
            "min_w"  : size.width,
            "min_h"  : size.height,

        }
        
        context = RequestContext(request, context)
        
        return render_to_response("admin/upload.html", context)

    # No more cropping to be done, close out
    else :
        image_thumbs = [image.thumbnail_url(size.slug) for size in image.size_set.get_size_by_ratio()] 
    
        context = {
            "image": image,
            "image_thumbs": image_thumbs,
            "image_element_id" : request.GET["image_element_id"]
        }
        
        context = RequestContext(request, context)
        return render_to_response("admin/complete.html", context)
        
