# FROM THE FUTURE LOL
from __future__ import division

import os
import sys

from django import forms
from django.conf import settings
from django.http import HttpResponse, HttpResponseServerError, Http404
from django.shortcuts import render_to_response
from django.template import RequestContext
from django.core.cache import cache
from django.core.urlresolvers import reverse
from django.utils.datastructures import MultiValueDictKeyError
from django.views.decorators.csrf import csrf_exempt
from jsonutil import jsonutil

import Image

from cropduster.handlers import UploadProgressCachedHandler
from cropduster.utils import get_image_extension, get_min_size, get_relative_media_url, get_upload_foldername, rescale, create_cropped_image, OrderedDict, ImagePath
from cropduster.models import Image as CropDusterImage
from cropduster.settings import CROPDUSTER_MEDIA_ROOT
from cropduster.exceptions import CropDusterException, CropDusterUrlException, CropDusterViewException

import simplejson
import re

import logging
from sentry.client.handlers import SentryHandler

logger = logging.getLogger('root')
logger.addHandler(SentryHandler())

# For validation
class UploadForm(forms.Form):
	picture = forms.ImageField(required=True)
	
@csrf_exempt
def upload(request):

	if request.method == "GET":
		return render_upload_form(request)
	else:
		return render_upload(request)


def render_upload_form(request):
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
		'image_id':'',
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
		image_path = ImagePath(image.path)
		
		context_data['image_id'] = image.pk
		context_data['orig_image'] = image_path.original_url_path
		
		# @todo Check that orig_image exists, as cropping won't work
		# in the next step if it doesn't

		context_data['image'] = image_path.preview_url_path

		(orig_w, orig_h) = image.get_image_size()
		context_data['orig_w'] = orig_w
		context_data['orig_h'] = orig_h
	except:
		pass
	

	# if getting to the page not from an upload
	if 'image_path' in request.GET:
		image_path = ImagePath('', url_path=request.GET['image_path'])
		
		context_data['image'] = image_path.original_url_path
		context_data['image_id'] = request.GET['image_id']
		context_data['orig_w'] = request.GET['w']
		context_data['orig_h'] = request.GET['h']
		context_data['orig_image'] = image_path.original_url_path

	# If we have a new image that hasn't been saved yet
	try:
		ext = request.GET['ext']
		
		path = ImagePath(request.GET['path'], extension=ext)
		
		
		if path.file_exists('_preview', ext):
			
			img = Image.open(path.original_system_path)
			
			(orig_w, orig_h) = img.size
			context_data['orig_w'] = orig_w
			context_data['orig_h'] = orig_h
			context_data['orig_image'] = path.original_url_path
			context_data['image'] =  path.preview_url_path
	except:
		pass
	
	context = RequestContext(request, context_data)
	
	try:
		crop_path = reverse('cropduster.views.crop')
		curr_path = request.META['PATH_INFO']
		
		if re.search(r"^/admin/", crop_path) and not re.search(r"^/admin/", curr_path):
		
			raise CropDusterUrlException("django.core.urlresolvers.reverse() is incorrectly" \
			+ " prepending /admin/ to cropduster.views.crop")
			
	except CropDusterException, e:
		_log_error(request, 'upload', action="reversing cropduster.views.crop", errors=[e])
		
	
	return render_to_response('cropduster/upload.html', context)

def render_upload(request):

	if hasattr(settings, 'CACHE_BACKEND'):
		request.upload_handlers.insert(0, UploadProgressCachedHandler(request))

	form = UploadForm(request.POST, request.FILES)

	if not form.is_valid():
		
		return _json_error(request, 'upload', action="uploading file", errors=form['picture'].errors)
		
	else:
		file = request.FILES['picture']
		
		file_name, extension = os.path.splitext(file.name)
		
		extension = extension.lower()
		
		image_path = get_upload_foldername(file.name)
		
		destination = open(image_path.tmp_system_path, 'wb+')

		for chunk in file.chunks():
			destination.write(chunk)
		destination.close()
		
		img = Image.open(image_path.tmp_system_path)
		
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
			return _json_error(request, 'upload', action="uploading file", errors=[error_msg])
			
		
		
		# File is good, get rid of the tmp file
		os.rename(image_path.tmp_system_path, image_path.original_system_path)
		
		# First pass resize if it's too large
		# (height > 500 px or width > 800 px)
		resize_ratio = min(800/w, 500/h)
		if resize_ratio < 1:
			w = int(round(w * resize_ratio))
			h = int(round(h * resize_ratio))
			img = rescale(img, w, h, crop=False)
	
		img_save_params = {}
		if img.format == 'JPEG':
			img_save_params['quality'] = 95
		
		try:
			img.save(image_path.preview_system_path, **img_save_params)
		except KeyError, e:
			# The user uploaded an image with an invalid file extension, we need
			# to rename it with the proper one.
			
			original_image = image_path.original_system_path
			
			image_path.extension = get_image_extension(img)
			
			os.rename(original_image, image_path.original_system_path)
		
			img.save(image_path.preview_system_path, **img_save_params)
	
		
		data = {
			'url': image_path.preview_url_path,
			'orig_width': orig_w,
			'orig_height': orig_h,
			'width': w,
			'height': h,
			'orig_url': image_path.original_url_path,
		}
		return HttpResponse(simplejson.dumps(data))



def _format_error(error):
	error_type = type(error).__name__
	if error_type == 'str' or error_type == 'unicode':
		return error
	elif error_type == 'IOError':
		exception_msg = str(error)
		matches = re.search(r"No such file or directory: u'(.+)'$", exception_msg)
		if matches is not None:
			file_name = matches.group(1)
			try:
				rel_file_name = get_relative_media_url(file_name)
				file_name = rel_file_name
			except:
				pass
			return "Could not find file " + file_name
	try:
		return ("[%s] %s" % (error_type, str(error)))
	except:
		return error

def _log_error(request, view, action, errors):
	# We only log the first error, send the rest as data; it's simpler this way
	error_msg = "Error %s: %s" % (action, _format_error(errors[0]))
	error_type = type(errors[0]).__name__
	
	log_kwargs = {}
	
	if error_type != 'str' and error_type != 'unicode':
		log_kwargs["exc_info"] = sys.exc_info()
	
	extra_data = {
		'errors': errors,
		'process_id': os.getpid()
	}	
	
	try:
		import psutil, math, time, thread
		p = psutil.Process(os.getpid())
		proc_timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(p.create_time))
		create_usec = ''
		try:
			create_usec = str(p.create_time - math.floor(p.create_time))[1:5]
		except:
			pass
		proc_timestamp += create_usec
		extra_data['process_create_date'] = proc_timestamp
		extra_data['thread_id'] = thread.get_ident()
	except ImportError:
		pass
	
	if error_type == 'CropDusterUrlException':
		from django.contrib import admin
		from django.core.urlresolvers import get_urlconf,get_resolver
		from django.utils.encoding import force_unicode
		urlconf = get_urlconf()
		resolver = get_resolver(urlconf)
		extra_data['resolver_data'] = {
			"regex": resolver.regex,
			"urlconf_name": resolver.urlconf_name,
			"default_kwargs": resolver.default_kwargs,
			"namespace": resolver.namespace,
			"urlconf_module": resolver.urlconf_module
		}
		resolver_reverse_dict = {}
		try:
			for key in resolver.reverse_dict.keys():
				unicode_key = unicode(force_unicode(key))
				resolver_reverse_dict[unicode_key] = resolver.reverse_dict[key]
		except:
			pass
		
		resolver_namespace_dict = {}
		try:
			for key in resolver.namespace_dict.keys():
				unicode_key = unicode(force_unicode(key))
				resolver_namespace_dict[unicode_key] = resolver.namespace_dict[key]
		except:
			pass
	
		
		extra_data['resolver_reverse_dict'] = resolver_reverse_dict
		extra_data['resolver_namespace_dict'] = resolver_namespace_dict
		extra_data['resolver_app_dict'] = resolver.app_dict
		extra_data['resolver_url_patterns'] = resolver.url_patterns
		extra_data['urlconf'] = urlconf
	
	logger.error(
		error_msg,
		extra = {
			'request': request,
			'view': 'cropduster.views.%s' % view,
			'url': request.path_info,
			'data': extra_data
		},
		**log_kwargs
	)

def _json_error(request, view, action, errors, log_error=False):
	if log_error:
		_log_error(request, view, action, errors)
			
	if len(errors) == 1:
		error_msg = "Error %s: %s" % (action, _format_error(errors[0]))
	else:
		error_msg =  "Errors %s: " % action
		error_msg += "<ul>"
		for error in errors:
			error_msg += "<li>&nbsp;&nbsp;&nbsp;&bull;&nbsp;%s</li>" % format_error(error)
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
	try:
		if request.method == "GET":
			raise CropDusterViewException("Form submission invalid")
		
		path = settings.PROJECT_ROOT + request.POST['orig_image']
		
	except CropDusterViewException, e:
		return _json_error(request, 'crop',
			action="cropping image", errors=[e], log_error=True)
	except MultiValueDictKeyError, e:
		return _json_error(request, 'crop',
			action="cropping image", errors=["Form submission contained no data"])
	
	#@todo Check orig_image is in fact a path before passing it to create_cropped_image
	file_root, file_ext = os.path.splitext(path)
	
	# all we need is the folder name, not the last file name
	file_dir, file_prefix = os.path.split(file_root)

	x = int(request.POST['x'])
	y = int(request.POST['y'])
	w = int(request.POST['w'])
	h = int(request.POST['h'])
	
	
	
	try:
		img = create_cropped_image(path, x=x, y=y, w=w, h=h)
	except Exception, e:
		return _json_error(request, 'crop', action="creating cropped image", errors=[e], log_error=True)
	
	default_thumb = request.POST['default_thumb']
	rel_url_path = request.POST['orig_image']

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
		try:
			db_image = CropDusterImage(
				crop_x = x,
				crop_y = y,
				crop_w = w,
				crop_h = h,
				path = request.POST['orig_image'],
				default_thumb = default_thumb
			)
			db_image.path = file_path
			file_name, db_image.extension = os.path.splitext(file_full_name)
		except Exception, e:
			return _json_error(request, 'crop', action="saving cropped image", errors=[e])
	
	thumb_ids = OrderedDict({})
	
	try:
		sizes = jsonutil.loads(request.POST['sizes'])
		auto_sizes = jsonutil.loads(request.POST['auto_sizes'])
	except Exception, e:
		return _json_error(request, 'crop', action="reading POST data", errors=[e])
	
	try:
		new_ids = _generate_and_save_thumbs(
			db_image,
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
	except Exception, e:
		return _json_error(request, 'crop', action="generating cropped thumbnails", errors=[e])
	
	thumb_urls = OrderedDict({})
	for size_name in thumb_ids:
		thumb_urls[size_name] = db_image.get_image_url(size_name, use_temp=True)
	
	data = {
		'id': db_image.id,
		'sizes': request.POST['sizes'],
		'image': request.POST['orig_image'],
		'image_id': db_image.id,
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
	#if not was_modified_since(request.META.get('HTTP_IF_MODIFIED_SINCE'),
	#						  statobj[stat.ST_MTIME], statobj[stat.ST_SIZE]):
	#	return HttpResponseNotModified(mimetype=mimetype)
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

	img_save_params = {}
	if img.format == 'JPEG':
		img_save_params['quality'] = 95
	
	for size_name in sizes:
		size = sizes[size_name]
		thumb_w = int(size[0])
		thumb_h = int(size[1])

		thumb = img.copy()
		if is_auto is False:
			thumb = rescale(thumb, thumb_w, thumb_h, crop=False)
		else:
			thumb = rescale(img, thumb_w, thumb_h)

		# Save to the real thumb_path if the image is new

		thumb_path = file_dir + '/' + size_name + file_ext
		if not os.path.exists(thumb_path):
			thumb.save(thumb_path, **img_save_params)

		thumb_tmp_path = file_dir + '/' + size_name + '_tmp' + file_ext

		thumb.save(thumb_tmp_path, **img_save_params)

		db_thumb = db_image.save_thumb(
			width = thumb_w,
			height = thumb_h,
			name = size_name
		)
		thumb_ids[size_name] = db_thumb.id

	return thumb_ids