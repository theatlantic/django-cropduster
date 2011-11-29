import os
from django.http import HttpResponse, Http404
from django.shortcuts import render_to_response
from django.template import RequestContext
from django.forms import TextInput
from django.forms.widgets import Select
from django.views.decorators.csrf import csrf_exempt

from cropduster.models import Image as CropDusterImage, Crop, Size, SizeSet
from cropduster.settings import CROPDUSTER_MEDIA_ROOT

import Image as pil

import logging
from sentry.client.handlers import SentryHandler
logger = logging.getLogger("root")
logger.addHandler(SentryHandler())

from django.forms import ModelForm, ValidationError

BROWSER_WIDTH = 800


# Create the form class.
class ImageForm(ModelForm):
	class Meta:
		model = CropDusterImage
	def clean(self):
		size_set = self.cleaned_data.get("size_set") or self.instance.size_set
		if any(self.errors):
			# Don't bother validating the formset unless each form is valid on its own
			logger.error(self.errors)
		image = self.cleaned_data.get("image")
		
		if image:		
			pil_image = pil.open(image)
		
			for size in size_set.size_set.all():
				if not size.auto_size and (size.width > pil_image.size[0] or size.height > pil_image.size[1]):
					raise ValidationError("Uploaded image (%s x %s) is smaller than a required thumbnail size: %s" % (pil_image.size[0], pil_image.size[1], size))
		return self.cleaned_data
		
		
class CropForm(ModelForm):
	class Meta:
		model = Crop		
		widgets = {
			"image": TextInput(),
		}
	def clean(self):
		if int(self.data["crop_x"]) < 0 or int(self.data["crop_y"]) < 0:
			self._errors.clear()
			raise ValidationError("Crop positions must be non-negative")
		
		return self.cleaned_data

def handle_error(request, formset):
	errors = formset.errors.values()[0]
	context = {
			"errors": errors,
			"formset": formset,
			"image_element_id" : request.GET["image_element_id"]
		}

	context = RequestContext(request, context)

	return render_to_response("admin/upload.html", context)
	
	
@csrf_exempt
def upload(request):
	
	size_set = SizeSet.objects.get(id=request.GET["size_set"])
	
	# get the current aspect ratio
	if "aspect_ratio_id" in request.POST:
		aspect_ratio_id = int(request.POST["aspect_ratio_id"])
	else:
		aspect_ratio_id = 0
	
	
	if "image_id" in request.GET:
		image = CropDusterImage.objects.get(id=request.GET["image_id"])
	elif "image_id" in request.POST:
		image = CropDusterImage.objects.get(id=request.POST["image_id"])
	else:
		image = CropDusterImage(size_set=size_set)
	

	
	size = Size.objects.get_size_by_ratio(size_set.id, aspect_ratio_id) or Size()
	

	#get the current crop
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
			formset = ImageForm(request.POST, request.FILES, instance=image)
			if formset.is_valid():
				image = formset.save()
				crop.image = image
			else:
				handle_error(request, formset)
				
			crop_formset = CropForm(instance=crop)
		else:
					
			#If its the first frame, get the image formset and save it (for attribution)
			if aspect_ratio_id ==0:
				formset = ImageForm(request.POST, instance=image)
				if formset.is_valid():
					formset.save()
			else:
				formset = ImageForm(instance=image)
				
			#if there's no cropping to be done, then just complete the process
			if size.id:
				
				#Lets save the crop
				request.POST['size'] = size.id
				request.POST['image'] = image.id
				crop_formset = CropForm(request.POST, instance=crop)
				
				if crop_formset.is_valid():
					crop = crop_formset.save()
					
					#Now get the next crop if it exists
					aspect_ratio_id = aspect_ratio_id + 1
					size = Size.objects.get_size_by_ratio(size_set, aspect_ratio_id)
					
					# if there's another crop
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
			
	#nothing being posted, get the image and form if they exist
	else:
		formset = ImageForm(instance=image)
		crop_formset = CropForm(instance=crop)
		
	# if theres more cropping to be done or its the first frame,
	# show the upload/crop form
	if (size and size.id) or request.method != "POST":		
		
		crop_w = crop.crop_w or size.width
		crop_h = crop.crop_h or size.height
		
		#combine errors from both forms, eliminate duplicates
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
			"crop_x" : crop.crop_x,
			"crop_y" : crop.crop_y,
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

	# no more cropping to be done, close out
	else :
		image_thumbs = [image.thumbnail_url(size.slug) for size in image.size_set.get_size_by_ratio()] 
	
		context = {
			"image": image,
			"image_thumbs": image_thumbs,
			"image_element_id" : request.GET["image_element_id"]
		}
		
		context = RequestContext(request, context)
		return render_to_response("admin/complete.html", context)
		

