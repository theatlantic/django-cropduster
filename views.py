# FROM THE FUTURE LOL
from __future__ import division

import os

from django import forms
from django.conf import settings
from django.core.urlresolvers import reverse
from django.http import HttpResponse, HttpResponseServerError, Http404, HttpResponseNotModified
from django.shortcuts import render_to_response
from django.template import RequestContext
from django.core.cache import cache
from django.views.decorators.csrf import csrf_exempt

from jsonutil import jsonutil

import Image

from cropduster.handlers import UploadProgressCachedHandler
from cropduster.utils import *
from cropduster.models import Image as CropDusterImage, Thumb as CropDusterThumb
from cropduster.settings import *

import simplejson

# For validation
class UploadForm(forms.Form):
	picture = forms.ImageField(required=True)
	

@csrf_exempt
def upload(request):
	if request.method == "GET":
		try:	
			image_element_id = request.GET['el_id']
		except:
			image_element_id = ""
		
		media_url = reverse('cropduster-static', kwargs={'path':''})
		
		context_data = 	{
			'is_popup': True,
			'image_element_id': image_element_id,
			'image': os.path.join(media_url, 'img/blank.gif'),
			'orig_image': '',
			'x': 0,
			'y': 0,
			'w': 0,
			'h': 0
		}
		
		try:
			context_data['x'] = request.GET['x']
			context_data['y'] = request.GET['y']
			context_data['w'] = request.GET['w']
			context_data['h'] = request.GET['h']
		except:
			pass
		
		try:
			image_id = request.GET['id']
			image = CropDusterImage.objects.get(pk=image_id)
			context_data['image_id'] = image.pk
			context_data['orig_image'] = os.path.join(image.path, 'original' + image.extension)
			# @todo Check that orig_image exists, as cropping won't work
			# in the next step if it doesn't

			context_data['image'] = image.get_image_url('_preview')

			(orig_w, orig_h) = image.get_image_size()
			context_data['orig_w'] = orig_w
			context_data['orig_h'] = orig_h
		except:
			pass
		
		# If we have a new image that hasn't been saved yet
		try:
			path = request.GET['path']
			root_path = os.path.join(settings.STATIC_ROOT, path)
			ext = request.GET['ext']
			if os.path.exists(os.path.join(root_path, '_preview' + '.' + ext)):
				orig_image = os.path.join(path, 'original' + '.' + ext)
				context_data['orig_image'] = orig_image
				preview_url = settings.STATIC_URL + '/' + path + '/_preview' + '.' + ext
				import re
				# Remove double '/'s
				preview_url = re.sub(r'(?<!:)/+', '/', preview_url)
				context_data['image'] = preview_url
				img = Image.open(os.path.join(settings.STATIC_ROOT, orig_image))
				(orig_w, orig_h) = img.size
				context_data['orig_w'] = orig_w
				context_data['orig_h'] = orig_h
		except:
			pass
		
		context = RequestContext(request, context_data)
		return render_to_response('cropduster/upload.html', context)
	else:
		if hasattr(settings, 'CACHE_BACKEND'):
			request.upload_handlers.insert(0, UploadProgressCachedHandler(request))
	
		form = UploadForm(request.POST, request.FILES)

		if not form.is_valid():
			return _upload_error(form['picture'].errors)
		
		else:
			file = request.FILES['picture'];
			file_name, extension = os.path.splitext(file.name)
			extension = extension.lower()
			folder_path = get_upload_foldername(file.name)
			
			tmp_file_path = os.path.join(folder_path, '__tmp' + extension)
			
			
			destination = open(tmp_file_path, 'wb+')

			for chunk in file.chunks():
				destination.write(chunk)
			destination.close()
			
			img = Image.open(tmp_file_path)
			
			(w, h) = img.size
			(orig_w, orig_h) = img.size
			(min_w, min_h) = get_min_size(request.POST['sizes'], request.POST['auto_sizes'])
			if (orig_w < min_w or orig_h < min_h):
				error_msg = """
					Image must be at least %(min_w)sx%(min_h)s (%(min_w)s pixels wide and
					%(min_h)s pixels high). The image you uploaded was %(orig_w)sx%(orig_h)s pixels.
				""" % {
					"min_w": str(min_w),
					"min_h": str(min_h),
					"orig_w": orig_w,
					"orig_h": orig_h
				}
				return _upload_error([error_msg])
			
			# File is good, get rid of the tmp file
			orig_file_path = os.path.join(folder_path, 'original' + extension)
			os.rename(tmp_file_path, orig_file_path)
			
			orig_url = get_media_url(orig_file_path)

			# First pass resize if it's too large
			# (height > 500 px or width > 800 px)
			resize_ratio = min(800/w, 500/h)
			if resize_ratio < 1:
				w = int(round(w * resize_ratio))
				h = int(round(h * resize_ratio))
				img.thumbnail((w, h), Image.ANTIALIAS)
		
			preview_file_path = os.path.join(folder_path, '_preview' + extension)
			img.save(preview_file_path)
		
			data = {
				'url': get_media_url(preview_file_path),
				'orig_width': orig_w,
				'orig_height': orig_h,
				'width': w,
				'height': h,
				'orig_url': orig_url,
			}
			return HttpResponse(simplejson.dumps(data))

def _upload_error(errors):
	if len(errors) == 1:
		error_msg = "Error with uploaded file: " + errors[0]
	else:
		error_msg =  "Errors with file upload:"
		error_msg += "<ul>"
		for error in errors:
			error_msg += "<li>&nbsp;&nbsp;&nbsp;&bull;&nbsp;" + error + "</li>"
		error_msg += "</ul>"
	data = {
		'error': error_msg
	}
	return HttpResponse(simplejson.dumps(data))

def upload_progress(request):
	"""
	Return JSON object with information about the progress of an upload.
	"""
	progress_id = ''
	if 'X-Progress-ID' in request.GET:
		progress_id = request.GET['X-Progress-ID']
	elif 'X-Progress-ID' in request.META:
		progress_id = request.META['X-Progress-ID']
	if progress_id:
		cache_key = "%s_%s" % (request.META['REMOTE_ADDR'], progress_id)
		data = cache.get(cache_key)
		return HttpResponse(jsonutil.dumps(data))
	else:
		return HttpResponseServerError('Server Error: You must provide X-Progress-ID header or query param.')

@csrf_exempt
def crop(request):
	path = get_media_path(request.POST['orig_image'])
	
	#@todo Check orig_image is in fact a path before passing it to create_cropped_image
	file_root, file_ext = os.path.splitext(path)
	
	# all we need is the folder name, not the last file name
	file_dir, file_prefix = os.path.split(file_root)

	x = int(request.POST['x'])
	y = int(request.POST['y'])
	w = int(request.POST['w'])
	h = int(request.POST['h'])
	
	
	img = create_cropped_image(path, x=x, y=y, w=w, h=h)
	
	default_thumb = request.POST['default_thumb']
	rel_url_path = get_relative_media_url(request.POST['orig_image'])

	file_path, file_full_name = os.path.split(rel_url_path)
	
	# If there is an image_id passed, update the existing object
	try:
		db_image = CropDusterImage.objects.get(path=file_path)
		db_image.crop_x = x
		db_image.crop_y = y
		db_image.crop_w = w
		db_image.crop_h = h		
		db_image.default_thumb = default_thumb
	except:
		db_image = CropDusterImage(
			crop_x = x,
			crop_y = y,
			crop_w = w,
			crop_h = h,
			path = get_relative_media_url(request.POST['orig_image']),
			default_thumb = default_thumb
		)
		db_image.path = file_path
		file_name, db_image.extension = os.path.splitext(file_full_name)
	
	thumb_ids = OrderedDict({})
	
	sizes = jsonutil.loads(request.POST['sizes'])
	auto_sizes = jsonutil.loads(request.POST['auto_sizes'])
	
	new_ids = _generate_and_save_thumbs(db_image,
			sizes,
			img,
			file_dir,
			file_ext
	)
	thumb_ids.update(new_ids)
	
	if auto_sizes is not None:
		new_ids = _generate_and_save_thumbs(db_image,
				auto_sizes,
				img,
				file_dir,
				file_ext,
				is_auto=True
		)
		thumb_ids.update(new_ids)
	
	thumb_urls = OrderedDict({})
	for size_name in thumb_ids:
		thumb_urls[size_name] = db_image.get_image_url(size_name, use_temp=True)
	
	data = {
		'id': db_image.id,
		'sizes': request.POST['sizes'],
		'image': request.POST['orig_image'],
		'thumb_urls': jsonutil.dumps(thumb_urls),
		'default_thumb': db_image.default_thumb,
		'filename': db_image.get_base_dir_name() + db_image.extension,
		'extension': db_image._extension,
		'path': db_image.path,
		'thumbs': jsonutil.dumps(thumb_ids),
		'x': request.POST['x'],
		'y': request.POST['y'],
		'w': request.POST['w'],
		'h': request.POST['h']
	}
	if data['id'] is None:
		try:
			data['id'] = request.POST['image_id']
		except:
			# blank id will force generate a new one on the parent page
			data['id'] = ''
	return HttpResponse(jsonutil.dumps(data))

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
	path = path.lstrip('/')
	newpath = ''
	for part in path.split('/'):
		if not part:
			# Strip empty path components.
			continue
		drive, part = os.path.splitdrive(part)
		head, part = os.path.split(part)
		if part in (os.curdir, os.pardir):
			# Strip '.' and '..' in path.
			continue
		newpath = os.path.join(newpath, part).replace('\\', '/')
	if newpath and path != newpath:
		return HttpResponseRedirect(newpath)
	fullpath = os.path.join(document_root, newpath)
	if os.path.isdir(fullpath):
		raise Http404("Directory indexes are not allowed here.")
	if not os.path.exists(fullpath):
		raise Http404('"%s" does not exist' % fullpath)
	# Respect the If-Modified-Since header.
	statobj = os.stat(fullpath)
	mimetype = mimetypes.guess_type(fullpath)[0] or 'application/octet-stream'
	if not was_modified_since(request.META.get('HTTP_IF_MODIFIED_SINCE'),
							  statobj[stat.ST_MTIME], statobj[stat.ST_SIZE]):
		return HttpResponseNotModified(mimetype=mimetype)
	contents = open(fullpath, 'rb').read()
	response = HttpResponse(contents, mimetype=mimetype)
	response["Last-Modified"] = http_date(statobj[stat.ST_MTIME])
	response["Content-Length"] = len(contents)
	return response

def _generate_and_save_thumbs(db_image, sizes, img, file_dir, file_ext, is_auto=False):
	'''
	Loops through the sizes given and saves a thumbnail for each one. Returns
	a dict of key value pairs with size_name, thumbnail_id
	'''
	thumb_ids = {}
	
	for size_name in sizes:
		size = sizes[size_name]
		thumb_w = int(size[0])
		thumb_h = int(size[1])
		
		if is_auto is False:
			thumb = img.copy()	
		else:
			thumb = rescale(img, thumb_w, thumb_h)
		
		thumb.thumbnail((thumb_w, thumb_h), Image.ANTIALIAS)
		
		# Save to the real thumb_path if the image is new
		
		thumb_path = file_dir + '/' + size_name + file_ext
		if not os.path.exists(thumb_path):
			thumb.save(thumb_path)
		
		thumb_tmp_path = file_dir + '/' + size_name + '_tmp' + file_ext
		
		thumb.save(thumb_tmp_path)
		
		db_thumb = db_image.save_thumb(
			width = thumb_w,
			height = thumb_h,
			name = size_name
		)
		thumb_ids[size_name] = db_thumb.id
	
	return thumb_ids