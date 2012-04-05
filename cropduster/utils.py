from PIL import Image
from decimal import Decimal

def aspect_ratio(w, h):
	if not h or not w:
		return 1
	else:
		return Decimal(str(round(float(w)/float(h), 2)))




def rescale(img, w=0, h=0, auto_crop=True, **kwargs):
	"""Rescale the given image, optionally cropping it to make sure the result image has the specified width and height."""
		
	if w <= 0:
		w = float(img.size[0] * h) /float(img.size[1])
	if h <= 0:
		h = float(img.size[1] * w) /float(img.size[0])

	max_width = w
	max_height = h

	src_width, src_height = img.size
	
	src_ratio = float(src_width) / float(src_height)
	
	dst_width, dst_height = max_width, max_height
	
	dst_ratio = float(dst_width) / float(dst_height)

	if auto_crop:
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
			int(x_offset + crop_width), 
			int(y_offset + crop_height)
		))

	# if not cropping, don't squish, use w/h as max values to resize on
	else:
		if (src_ratio * w) > h:
			dst_width = src_ratio * h
			dst_height = h
		else:
			dst_width = w
			dst_height = w/src_ratio
			
		img = img.resize((int(dst_width), int(dst_height)), Image.ANTIALIAS)

	return img

def create_cropped_image(path=None, x=0, y=0, w=0, h=0):
	if path is None:
		raise ValueError("A path must be specified")

	img = Image.open(path)
	img.copy()
	img.load()
	img = img.crop((x, y, x + w, y + h))
	img.load()
	return img


def rescale_signal(sender, instance, created, max_height=None, max_width=None, **kwargs):
	""" Simplified image resizer meant to work with post-save/pre-save tasks """

	max_width = max_width
	max_height = max_height
	
	if not max_width and not max_height:
		raise ValueError("Either max width or max height must be defined")
		
	if max_width and max_height:
		raise ValueError("To avoid improper scaling, only define a width or a height, not both")

	if instance.image:

		im = Image.open(instance.image.path)
		
		if max_width:
			height = instance.image.height * max_width/instance.image.width
			size = max_width, height
			
		if max_height:
			width = instance.image.width * max_height/instance.image.height
			size = width, max_height
		
		im.thumbnail(size, Image.ANTIALIAS)
		
		im.save(instance.image.path)