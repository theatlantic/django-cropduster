from django.http import HttpResponse, Http404
from django.shortcuts import render_to_response
from django.template import RequestContext
from django.views.decorators.csrf import csrf_exempt

from cropduster.models import Image as CropDusterImage, Crop, Size, SizeSet
from cropduster.settings import CROPDUSTER_MEDIA_ROOT

import Image as pil

import logging
from sentry.client.handlers import SentryHandler
logger = logging.getLogger("root")
logger.addHandler(SentryHandler())

from django.forms import ModelForm, ValidationError


# Create the form class.
class ImageForm(ModelForm):
	class Meta:
		model = CropDusterImage
	
	def clean(self):

		size_set = self.cleaned_data.get("size_set")
		if any(self.errors):
			# Don't bother validating the formset unless each form is valid on its own
			logger.error(self.errors)
		image = self.cleaned_data.get("image")
		if not image:
			raise ValidationError("Invalid image: %s" % self.errors)
		
		
		large_enough = True
		
		pil_image = pil.open(image)

		for size in size_set.size_set.all():
			if not size.auto_size and (size.width > pil_image.size[0] or size.height > pil_image.size[1]):
				raise ValidationError("Uploaded image is smaller than a required thumbnail size: %s" % size)
		return self.cleaned_data
		
		
class CropForm(ModelForm):
	class Meta:
		model = Crop
		

def error(request, formset):

	context = {
			"errors": formset.errors,
			"formset": formset,
			"image_element_id" : request.GET["image_element_id"]
		}
		
	context = RequestContext(request, context)
	
	return render_to_response("cropduster/upload.html", context)
		
	
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
	

	
	size = Size.objects.get_size_by_ratio(size_set.id, aspect_ratio_id)
	
	
	#get the current crop
	try:
		crop = Crop.objects.get(image=image.id, size=size.id)
	except:
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
				error(request, formset)
				
				
			crop_formset = CropForm(instance=crop)
		else:
			formset = ImageForm(instance=image)
			
			request.POST['size'] = size.id
			request.POST['image'] = image.id
			
			crop_formset = CropForm(request.POST, instance=crop)
			
			crop = crop_formset.save()
		
			aspect_ratio_id = aspect_ratio_id + 1
			size = Size.objects.get_size_by_ratio(size_set, aspect_ratio_id)
			if size:
				try:
					crop = Crop.objects.get(image=image.id, size=size.id)
					crop_formset = CropForm(instance=crop)
				except:
					crop_formset = CropForm()
			
	else:
		formset = ImageForm(instance=image)
		crop_formset = CropForm(instance=crop)
		
	

	if size:
		crop_w = crop.crop_w or size.width
		crop_h = crop.crop_h or size.height
		
		context = {
			"aspect_ratio_id": aspect_ratio_id,
			"image": image,
			"formset": formset,
			"crop_formset": crop_formset,
			"crop_w" : crop_w,
			"crop_h" : crop_h,
			"crop_x" : crop.crop_x,
			"crop_y" : crop.crop_y,
			"aspect_ratio": size.aspect_ratio,
			"image_element_id" : request.GET["image_element_id"]
		}
		
		context = RequestContext(request, context)
		
		return render_to_response("cropduster/upload.html", context)
		
	else:
		image_thumbs = [image.thumbnail_url(size.slug) for size in image.size_set.get_size_by_ratio()] 

		context = {
			"image": image,
			"image_thumbs": image_thumbs,
			"image_element_id" : request.GET["image_element_id"]
		}
		
		context = RequestContext(request, context)
		return render_to_response("cropduster/complete.html", context)

def static_media(request, path):
	"""
	Serve static files below a given point in the directory structure.
	"""
	from django.utils.http import http_date
	from django.views.static import was_modified_since
	import mimetypes
	import os.path
	import posixpath
	import stat
	import urllib

	document_root = os.path.join(CROPDUSTER_MEDIA_ROOT)
	
	path = posixpath.normpath(urllib.unquote(path))
	path = path.lstrip("/")
	newpath = ""
	for part in path.split("/"):
		if not part:
			# Strip empty path components.
			continue
		drive, part = os.path.splitdrive(part)
		head, part = os.path.split(part)
		if part in (os.curdir, os.pardir):
			# Strip "." and ".." in path.
			continue
		newpath = os.path.join(newpath, part).replace("\\", "/")
	if newpath and path != newpath:
		return HttpResponseRedirect(newpath)
	fullpath = os.path.join(document_root, newpath)
	if os.path.isdir(fullpath):
		raise Http404("Directory indexes are not allowed here.")
	if not os.path.exists(fullpath):
		raise Http404("'%s' does not exist" % fullpath)
	# Respect the If-Modified-Since header.
	statobj = os.stat(fullpath)
	mimetype = mimetypes.guess_type(fullpath)[0] or "application/octet-stream"
	#if not was_modified_since(request.META.get("HTTP_IF_MODIFIED_SINCE"),
	#						  statobj[stat.ST_MTIME], statobj[stat.ST_SIZE]):
	#	return HttpResponseNotModified(mimetype=mimetype)
	contents = open(fullpath, "rb").read()
	response = HttpResponse(contents, mimetype=mimetype)
	response["Last-Modified"] = http_date(statobj[stat.ST_MTIME])
	response["Content-Length"] = len(contents)
	return response

