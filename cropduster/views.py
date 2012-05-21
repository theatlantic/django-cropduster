import os
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
        widgets = {
            "image": TextInput(),
        }
    def clean(self):
        if not("crop_x" in self.data and "crop_y" in self.data):
            self._errors.clear()
            raise ValidationError("Missing crop values")
            
        if int(self.data["crop_x"]) < 0 or int(self.data["crop_y"]) < 0:
            self._errors.clear()
            raise ValidationError("Crop positions must be non-negative")
        
        return self.cleaned_data
    
@csrf_exempt
def _old_upload(request):
    
    size_set = SizeSet.objects.get(id=request.GET["size_set"])
    
    # Get the current aspect ratio
    if "aspect_ratio_id" in request.POST:
        aspect_ratio_id = int(request.POST["aspect_ratio_id"])
    else:
        aspect_ratio_id = 0
    
    
    if "image_id" in request.GET:
        image = CropDusterImage.objects.get(id=request.GET["image_id"])
    elif "image_id" in request.POST:
        image = CropDusterImage.objects.get(id=request.POST["image_id"])
    else:
        image = CropDusterImage()
        image.add_size_set(size_set)
    
    size = Size.objects.get_size_by_ratio(size_set.id, aspect_ratio_id) or Size()
    

    # Get the current crop
    try:
        crop = Crop.objects.get(image=image.id, size=size.id)
    except Crop.DoesNotExist:
        crop = Crop()
        crop.crop_w = size.width
        crop.crop_h = size.height
        crop.crop_x = 0
        crop.crop_y = 0
        crop.image = image
        crop.size = size

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
        formset = ImageForm(instance=image)
        crop_formset = CropForm(instance=crop)
        
    # If theres more cropping to be done or its the first frame,
    # show the upload/crop form
    if (size and size.id) or request.method != "POST":        
        
        crop_w = crop.crop_w or size.width
        crop_h = crop.crop_h or size.height
        
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
        
uploading_image = lambda r: r.method == 'POST' and request.FILES

def get_image(request):
    image_id = request.GET.get('image_id') or request.POST.get('image_id')
    if image_id is not None:
        image = CropDusterImage.objects.get(id=image_id)
    else:
        image = CropDusterImage()

    return image

def apply_sizes(image, size_set):
    sizes = []
    for i in image.add_size_set(size_set):
        s = i.size
        if not s.auto_crop:
            sizes.append(s.calc_dimensions(image.width, image.height))
        i.save()

    return sizes

def get_crops(sizes):
    crops = []
    for aspect_ratio, dimensions in categorize(sizes, lambda x: x[2]).iteritems():
        widths, heights, _ars = zip(*dimensions)
        crops.append((aspect_ratio, max(widths), max(heights)))

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

@csrf_exempt
def upload(request):
    
    size_set = SizeSet.objects.get(id=request.GET["size_set"])
    image = get_image(request)
   
    # Initial Get
    if request.method == 'GET' and not request.FILES:
        image_form = ImageForm(instance=image)
        metadata_form = MetadataForm()
        context = {'formset': image_form,
                   'metadata_form': metadata_form,
                   'image': image}
        return render_to_response("admin/upload.html", context)

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
        
