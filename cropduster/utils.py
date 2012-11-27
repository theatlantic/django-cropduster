from PIL import Image
from decimal import Decimal

def aspect_ratio(width, height):
	""" Defines aspect ratio from two sizes with consistent rounding method """
	
	if not height or not width:
		return 1
	else:
		return Decimal(str(round(float(width)/float(height), 2)))


def rescale(img, width=0, height=0, auto_crop=True, **kwargs):
	""" 
		Rescale the given image.  If one size is not given, image is scaled down at current aspect ratio
		img -- a PIL image object

		Auto-crop option does a dumb crop that chops the image to the needed size  
	"""
		
	if width <= 0:
		width = float(img.size[0] * height) /float(img.size[1])
		
	if height <= 0:
		height = float(img.size[1] * width) /float(img.size[0])

	max_width = width
	max_height = height

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

		img = img.resize((int(dst_width), int(dst_height)), Image.ANTIALIAS)

	# if not cropping, don't squish, use w/h as max values to resize on
	else:
		if (width / src_ratio) > height:
            # height larger than intended
			dst_width = width
			dst_height = width / src_ratio
		else:
            # width larger than intended
			dst_width = src_ratio * height
			dst_height = height

		img = img.resize((int(dst_width), int(dst_height)), Image.ANTIALIAS)
		img = img.crop([0, 0, int(width), int(height)])

	return img

def create_cropped_image(path=None, x=0, y=0, width=0, height=0):
	""" 
		Crop image given a starting (x, y) position and a width and height of the cropped area 
	"""
	
	if path is None:
		raise ValueError("A path must be specified")

	img = Image.open(path)
	img.copy()
	img.load()
	img = img.crop((x, y, x + width, y + height))
	img.load()
	
	return img

