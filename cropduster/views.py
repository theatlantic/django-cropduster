import os, io
from django.http import HttpResponse
from django.shortcuts import render_to_response
from django.template import RequestContext
from django.forms import TextInput
from django.views.decorators.csrf import csrf_exempt
from django.forms import ModelForm
from django.conf import settings

from cropduster.models import Image as CropDusterImage, Crop, Size, SizeSet
from cropduster.exif import process_file
from cropduster.utils import aspect_ratio

import json


BROWSER_WIDTH = 800
CROPDUSTER_EXIF_DATA = getattr(settings, "CROPDUSTER_EXIF_DATA", True)

def get_ratio(request): 
	return HttpResponse(json.dumps(
		[u"%s" % aspect_ratio(request.GET["width"], request.GET["height"])]
	))


# Create the form class.
class ImageForm(ModelForm):
	class Meta:
		model = CropDusterImage

		
class CropForm(ModelForm):
	class Meta:
		model = Crop		
		widgets = {
			"image": TextInput(),
		}

	
@csrf_exempt
def upload(request):
	
	size_set = SizeSet.objects.get(id=request.GET["size_set"])
	
	# Get the current aspect ratio
	if "aspect_ratio_id" in request.POST:
		aspect_ratio_id = int(request.POST["aspect_ratio_id"])
	else:
		aspect_ratio_id = 0
	
	
	
	image_id = None
	
	if "image_id" in request.GET:
		image_id = request.GET["image_id"]
	elif "image_id" in request.POST:
		image_id = request.POST["image_id"]
	
	try:
		image_id = int(image_id)
		image = CropDusterImage.objects.get(id=image_id)
	except ValueError:
		image = CropDusterImage(size_set=size_set)
	
		
		
	
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
				
				if CROPDUSTER_EXIF_DATA:
					# Check for exif data and use it to populate caption/attribution
					try:
						exif_data = process_file(io.BytesIO(b"%s" % formset.cleaned_data["image"].file.getvalue()))
					except AttributeError:
						exif_data = {}
						
					if not formset.cleaned_data["caption"] and "Image ImageDescription" in exif_data:
						formset.data["caption"] = exif_data["Image ImageDescription"].__str__()
					if not formset.cleaned_data["attribution"] and "EXIF UserComment" in exif_data:
						formset.data["attribution"] = exif_data["EXIF UserComment"].__str__()
				
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
					"image_element_id" : request.GET["image_element_id"],
					"static_url": settings.STATIC_URL,
				}
			
				context = RequestContext(request, context)
				
				return render_to_response("admin/upload.html", context)
						
			
		else:
					
			#If its the first frame, get the image formset and save it (for attribution)
			
			if not aspect_ratio_id:
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
			if error[0] != '__all__':
				string = u"%s: %s" % (error[0].capitalize(), error[1].as_text())
			else: 
				string = error[1].as_text()
			all_errors.append(string)
			
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
			"static_url": settings.STATIC_URL,

		}
		
		context = RequestContext(request, context)
		
		return render_to_response("admin/upload.html", context)

	# No more cropping to be done, close out
	else :
		image_thumbs = [image.thumbnail_url(size.slug) for size in image.size_set.get_unique_ratios()] 
	
		context = {
			"image": image,
			"image_thumbs": image_thumbs,
			"image_element_id" : request.GET["image_element_id"],
			"static_url": settings.STATIC_URL,
		}
		
		context = RequestContext(request, context)
		return render_to_response("admin/complete.html", context)
		

