import Image


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
