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

    $ pip install -e git+git://github.com/theatlantic/django-cropduster.git#egg=django-cropduster

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

In the admin.py for your app, to override the default widgets for that field,
and define which size sets to use by the handle of the size set:

```python
from cropduster.widgets import AdminCropdusterWidget
from cropduster.models import CropDusterField

class MyModelForm(forms.ModelForm):
    class Meta:
        model = MyModel
        widgets = {
            "cropduster_field": AdminCropdusterWidget(MyModel, "cropduster_field", "size-set-1"),
            # Any additional ones followingh
        }

class MyModelAdmin(admin.ModelAdmin):
    form = TestForm
```

Settings
--------
__CROPDUSTER_UPLOAD_PATH__: Relative path indicating where cropduster images should be stored.  Required.

__CROPDUSTER_TMP_DIR__: Path to where temporary images are stored.  If omitted, uses the default path.  Optional, but should be provided.

__CROPDUSTER_NORMALIZE_EXT__: Defaults to False.  If set to true, Cropduster will normalize file extensions based on their encoding format, stripping away erroneous file-type details.  Optional.

__CROPDUSTER_TRANSCODE__: Transcodes one image format into another when rendering derived images.  This is useful when raw images are uploaded that need to be stored in a more web appropriate format.  Optional.