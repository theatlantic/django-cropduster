import os
import hashlib

from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import models

from generic_plus.utils import get_relative_media_url

from cropduster import settings as cropduster_settings
from cropduster.fields import CropDusterField
from cropduster.files import VirtualFieldFile
from cropduster.resizing import Size


class StandaloneImageManager(models.Manager):

    def get_from_file(self, file_path, upload_to=None, preview_w=None, preview_h=None):
        from cropduster.models import Image
        from cropduster.views.forms import clean_upload_data

        image_file = VirtualFieldFile(file_path)
        md5 = hashlib.md5()
        image_contents = image_file.read()
        md5.update(image_contents)
        basepath, basename = os.path.split(file_path)
        basefile, extension = os.path.splitext(basename)
        if basefile == 'original':
            basepath, basename = os.path.split(basepath)
            basename += extension
        standalone, created = self.get_or_create(md5=md5.hexdigest().lower())
        if created or not standalone.image:
            file_data = clean_upload_data({
                'image': SimpleUploadedFile(basename, image_contents),
                'upload_to': upload_to,
            })
            file_path = get_relative_media_url(file_data['image'].name)
            standalone.image = file_path
            standalone.save()
        else:
            file_path = get_relative_media_url(standalone.image.name)

        cropduster_image, created = Image.objects.get_or_create(
            content_type=ContentType.objects.get_for_model(StandaloneImage),
            object_id=standalone.pk)
        standalone.image.related_object = cropduster_image
        cropduster_image.image = file_path
        cropduster_image.save()
        cropduster_image.save_preview(preview_w, preview_h)
        return standalone


class StandaloneImage(models.Model):

    objects = StandaloneImageManager()

    md5 = models.CharField(max_length=32)
    image = CropDusterField(sizes=[Size("crop")], upload_to='')

    class Meta:
        app_label = cropduster_settings.CROPDUSTER_APP_LABEL
        db_table = '%s_standaloneimage' % cropduster_settings.CROPDUSTER_DB_PREFIX

    def save(self, **kwargs):
        if not self.md5:
            md5_hash = hashlib.md5()
            with default_open(self.image.path, mode='rb') as f:
                md5_hash.update(f.read())
            self.md5 = md5_hash.digest()
        super(StandaloneImage, self).save(**kwargs)
