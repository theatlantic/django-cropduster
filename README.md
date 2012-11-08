django-cropduster
=================

**django-cropduster** is an image uploading and cropping tool for Django.
Integrates into the Django admin with an image file field, and then size sets
are created to correspond with the thumbnails to be created. On image upload,
it prompts to define a crop area and zoom for each aspect ratio from the size
set. Includes template tag to display images on the front end, and allows to
delay thumbnail creation until first request in template for rarely used
thumbnails.

Installation
------------

The recommended way to install from source is with pip:

    $ pip install -e git+git://github.com/ortsed/django-cropduster.git#egg=django-cropduster

If the source is already checked out, use setuptools:

    $ python setup.py install

**django-cropduster** requires the Python Imaging Library (PIL needs to be linked
with libjpeg and libpng in order to support JPG and PNG files).

Usage
-----

In models.py, define a field as a Cropduster image field:

```python
from cropduster.models import CropDusterField, Image as CropDusterImage

class MyModel(models.Model):
    image = CropDusterField(CropDusterImage)
```

Add Cropduster to the list of installed apps in the settings file:

```python
INSTALLED_APPS = (
    # ...
    'cropduster',
    # ...
)
```

Then, run syncdb and/or a South migration to create the database tables.

You can create the set of image sizes for use with your app in the Django
admin under Size Sets. Select "Crop on request" for images that should not be
created until they are first requested. "Auto size" means that the system will
not ask for a crop to be defined to create the thumbnail, but will simply be
created automatically (cropping from 0x0 to the image size, and then sizing
down).

In the admin.py for your app, override the default widget for that field,
and define which size set to use by the handle of the size set:

```python
from cropduster.widgets import AdminCropdusterWidget
from cropduster.models import CropDusterField

class MyModelAdmin(admin.ModelAdmin):
    formfield_overrides = {
        CropDusterField: {"widget": AdminCropdusterWidget("size-set-handle")}
    }
```

If you are using multiple cropduster fields with different size sets in the same 
admin page, you'll have to explicitly define the formfield based on the dbfield name

```python
class MyModelAdmin(admin.ModelAdmin):
    def formfield_for_dbfield(self, db_field, **kwargs):
        if db_field.name == 'image':
            kwargs['widget'] = AdminCropdusterWidget("series-graphic")
        elif db_field.name == 'banner_image':
            kwargs['widget'] = AdminCropdusterWidget("series-banner")
```



Optional Settings:

	CROPDUSTER_UPLOAD_PATH -- Sets the upload_to attribute for file uploads.  Otherwise defaults to MEDIA_ROOT.

	CROPDUSTER_EXIF_DATA -- Import embedded exif data for image attribution and caption.  Default = True.  Uses exif.py by Gene Cash / Thierry Bousch
