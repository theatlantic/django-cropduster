from __future__ import division

import os
import re

from datetime import datetime
from django.conf import settings
from cropduster.settings import *

from decimal import *

import Image

from django.template.defaultfilters import slugify 
import simplejson

IMAGE_EXTENSIONS = {
	"ARG":  ".arg",   "BMP":  ".bmp",   "BUFR": ".bufr",  "CUR":  ".cur",   "DCX":  ".dcx",
	"EPS":  ".ps",    "FITS": ".fit",   "FLI":  ".fli",   "FPX":  ".fpx",   "GBR":  ".gbr",
	"GIF":  ".gif",   "GRIB": ".grib",  "HDF5": ".hdf",   "ICNS": ".icns",  "ICO":  ".ico",
	"IM":   ".im",    "IPTC": ".iim",   "JPEG": ".jpg",   "MIC":  ".mic",   "MPEG": ".mpg",
	"MSP":  ".msp",   "Palm": ".palm",  "PCD":  ".pcd",   "PCX":  ".pcx",   "PDF":  ".pdf",
	"PNG":  ".png",   "PPM":  ".ppm",   "PSD":  ".psd",   "SGI":  ".rgb",   "SUN":  ".ras",
	"TGA":  ".tga",   "TIFF": ".tiff",  "WMF":  ".wmf",   "XBM":  ".xbm",   "XPM":  ".xpm",
}

def get_image_extension(img):
	if img.format in IMAGE_EXTENSIONS:
		return IMAGE_EXTENSIONS[img.format]
	else:
		# Our fallback is the PIL format name in lowercase,
		# which is probably the file extension
		fallback_ext = "." + img.format.lower()
		if fallback_ext in Image.EXTENSION:
			return fallback_ext
		exts = []
		for ext in Image.EXTENSION:
			if Image.EXTENSION[ext] == image.format:
				exts.append(ext)
		if len(exts) > 0:
			return exts[0]
		else:
			return fallback

def get_aspect_ratios(dims):
	ratios = []
	for name in dims.keys():
		(w, h) = dims[name]
		ratio = round(w / h, 2)
		ratio = Decimal(str(ratio)).quantize(Decimal('.1'), rounding=ROUND_HALF_DOWN)
		if ratio not in ratios:
			ratios.append(ratio)
	return ratios

def validate_sizes(sizes):
	valid_sizes_msg = "It must be a dict of two-valued tuples, each keyed on the thumbnail name."
	if sizes is None:
		raise ValueError("The sizes attribute is None. " + valid_sizes_msg)
	elif not isinstance(sizes, dict):
		raise ValueError("The sizes attribute is invalid. " + valid_sizes_msg)
	elif len(sizes.keys()) == 0:
		raise ValueError("The sizes attribute is empty " + valid_sizes_msg)
	
	for size_name in sizes:
		size = sizes[size_name]
		if not isinstance(size, tuple) and not isinstance(size, list):
			raise ValueError("The '%s' size is not a list or tuple; instead is type '%s'" % \
			                 (size_name, type(size).__name__) )
		if len(size) != 2:
			raise ValueError("The '%s' size is not a two-valued tuple, i.e. '(width, height)'" % size_name)
		if (not isinstance(size[0], int) or size[0] <= 0) or (not isinstance(size[1], int) or size[1] <= 0):
			raise ValueError("The '%s' size has a width or height that is not a positive integer." % size_name)

def get_largest_size(sizes):
	if isinstance(sizes, str) or isinstance(sizes, unicode):
		sizes = simplejson.loads(sizes)
	validate_sizes(sizes)
	max_w = 0
	max_h = 0
	for size_name, size in sizes.items():
		(w, h) = size
		max_w = max(w, max_w)
		max_h = max(h, max_h)
	return (max_w, max_h)

def get_min_size(*args):
	"""
	Minimum allowed width and height.
	hence why it is counter-intuitively the largest
	"""
	min_w = 0
	min_h = 0
	for sizes in args:
		if sizes is None or sizes == u'null':
			continue
		# The min width and height for
		# the image = the largest
		# width/height of the sizes/auto_sizes
		(largest_w, largest_h) = get_largest_size(sizes)
		min_w = max(largest_w, min_w)
		min_h = max(largest_h, min_h)
	return (min_w, min_h)


def get_media_path(url):
	"""
	Determine media URL's system file.
	"""
	url = url.replace(settings.STATIC_URL, '')
	path = os.path.abspath(settings.STATIC_ROOT) + '/' + url
	path = re.sub(r'(?<!:)/+', '/', path)
	return path

def get_relative_media_url(path):
	"""
	Determine system file's media URL without STATIC_URL prepended.
	"""
	url = path.replace(settings.STATIC_URL, '')
	relative_path = relpath(settings.STATIC_ROOT, settings.CROPDUSTER_UPLOAD_PATH)
	if re.match(r'\.\.', relative_path):
		raise Exception("Upload path is outside of static root")
	url = url.replace(relative_path, '')
	url = re.sub(r'(?<!:)/+', '/', url)
	url = re.sub(r'^/', '', url)
	return url

def get_media_url(path):
	"""
	Determine system file's media URL.
	"""
	url = settings.STATIC_URL + os.path.abspath(path).replace(os.path.abspath(settings.STATIC_ROOT), '')
	url = re.sub(r'(?<!:)/+', '/', url)
	return url

def get_available_name(dir_name, file_name):
	"""
	Create a folder based on file_name and return it.
	
	If a folder with file_name already exists in the given path,
	create a folder with a unique sequential number at the end.
	"""

	file_root, extension = os.path.splitext(file_name)

	file_root = slugify(file_root)

	name = os.path.join(dir_name, file_root)

	# If the filename already exists, keep adding a higher number 
	# to the folder name until the generated folder doesn't exist.
	i = 2
	while os.path.exists(name):
		# file_ext includes the dot.
		name = os.path.join(dir_name, file_root + '-' + str(i))
		i += 1
	
	os.makedirs(name)
		
	return name

def get_upload_foldername(file_name):
	# Generate date based path to put uploaded file.
	date_path = datetime.now().strftime('%Y/%m')

	# Complete upload path (upload_path + date_path).
	upload_path = os.path.join(settings.CROPDUSTER_UPLOAD_PATH, date_path)

	# Make sure upload_path exists.
	if not os.path.exists(upload_path):
		os.makedirs(upload_path)

	# Get available name and return.	
	return get_available_name(upload_path, file_name)

def rescale(img, w=0, h=0, crop=True):
	"""Rescale the given image, optionally cropping it to make sure the result image has the specified width and height."""

	if w <= 0 or h <= 0:
		raise ValueError("Width and height must be greater than zero")

	max_width = w
	max_height = h

	src_width, src_height = img.size
	src_ratio = float(src_width) / float(src_height)
	dst_width, dst_height = max_width, max_height
	dst_ratio = float(dst_width) / float(dst_height)

	if crop:
		if dst_ratio < src_ratio:
			crop_height = src_height
			crop_width = crop_height * dst_ratio
			x_offset = float(src_width - crop_width) / 2
			y_offset = 0
		else:
			crop_width = src_width
			crop_height = crop_width / dst_ratio
			x_offset = 0
			y_offset = float(src_height - crop_height) / 3
		img = img.crop((
			int(x_offset), 
			int(y_offset), 
			int(x_offset+crop_width), 
			int(y_offset+crop_height)
		))
	img = img.resize((int(dst_width), int(dst_height)), Image.ANTIALIAS)

	return img

def create_cropped_image(path=None, x=0, y=0, w=0, h=0):
	if path is None:
		raise ValueError("A path must be specified")
	if w <= 0 or h <= 0:
		raise ValueError("Width and height must be greater than zero")

	img = Image.open(path)
	img.copy()
	img.load()
	img = img.crop((x, y, x + w, y + h))
	img.load()
	return img

def pathsplit(p, rest=[]):
	(h,t) = os.path.split(p)
	if len(h) < 1: return [t]+rest
	if len(t) < 1: return [h]+rest
	return pathsplit(h,[t]+rest)

def commonpath(l1, l2, common=[]):
	if len(l1) < 1: return (common, l1, l2)
	if len(l2) < 1: return (common, l1, l2)
	if l1[0] != l2[0]: return (common, l1, l2)
	return commonpath(l1[1:], l2[1:], common+[l1[0]])

def relpath(p1, p2):
	"""
	Compute the relative path of one directory to another
	"""
	(common,l1,l2) = commonpath(pathsplit(p1), pathsplit(p2))
	p = []
	if len(l1) > 0:
		p = [ '../' * len(l1) ]
	p = p + l2
	return os.path.join( *p )

# From http://code.activestate.com/recipes/576693/

from UserDict import DictMixin

class OrderedDict(dict, DictMixin):
	
	def __init__(self, *args, **kwds):
		if len(args) > 1:
			raise TypeError('expected at most 1 arguments, got %d' % len(args))
		try:
			self.__end
		except AttributeError:
			self.clear()
		self.update(*args, **kwds)

	def clear(self):
		self.__end = end = []
		end += [None, end, end]		 # sentinel node for doubly linked list
		self.__map = {}				 # key --> [key, prev, next]
		dict.clear(self)

	def __setitem__(self, key, value):
		if key not in self:
			end = self.__end
			curr = end[1]
			curr[2] = end[1] = self.__map[key] = [key, curr, end]
		dict.__setitem__(self, key, value)

	def __delitem__(self, key):
		dict.__delitem__(self, key)
		key, prev, next = self.__map.pop(key)
		prev[2] = next
		next[1] = prev

	def __iter__(self):
		end = self.__end
		curr = end[2]
		while curr is not end:
			yield curr[0]
			curr = curr[2]

	def __reversed__(self):
		end = self.__end
		curr = end[1]
		while curr is not end:
			yield curr[0]
			curr = curr[1]

	def popitem(self, last=True):
		if not self:
			raise KeyError('dictionary is empty')
		if last:
			key = reversed(self).next()
		else:
			key = iter(self).next()
		value = self.pop(key)
		return key, value

	def __reduce__(self):
		items = [[k, self[k]] for k in self]
		tmp = self.__map, self.__end
		del self.__map, self.__end
		inst_dict = vars(self).copy()
		self.__map, self.__end = tmp
		if inst_dict:
			return (self.__class__, (items,), inst_dict)
		return self.__class__, (items,)

	def keys(self):
		return list(self)

	setdefault = DictMixin.setdefault
	update = DictMixin.update
	pop = DictMixin.pop
	values = DictMixin.values
	items = DictMixin.items
	iterkeys = DictMixin.iterkeys
	itervalues = DictMixin.itervalues
	iteritems = DictMixin.iteritems

	def __repr__(self):
		if not self:
			return '%s()' % (self.__class__.__name__,)
		return '%s(%r)' % (self.__class__.__name__, self.items())

	def copy(self):
		return self.__class__(self)

	@classmethod
	def fromkeys(cls, iterable, value=None):
		d = cls()
		for key in iterable:
			d[key] = value
		return d

	def __eq__(self, other):
		if isinstance(other, OrderedDict):
			return len(self)==len(other) and self.items() == other.items()
		return dict.__eq__(self, other)

	def __ne__(self, other):
		return not self == other