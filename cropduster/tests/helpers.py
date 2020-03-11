from io import open
import tempfile
import os
import shutil
import uuid

from django.conf import settings
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.test import override_settings

PATH = os.path.split(__file__)[0]
ORIG_IMG_PATH = os.path.join(PATH, 'data')


class CropdusterTestCaseMediaMixin(object):

    def _pre_setup(self):
        super(CropdusterTestCaseMediaMixin, self)._pre_setup()
        new_settings = {}
        self.temp_media_root = tempfile.mkdtemp(prefix='TEST_MEDIA_ROOT_')

        storage_cls = settings.DEFAULT_FILE_STORAGE

        if storage_cls == 'django.core.files.storage.FileSystemStorage':
            new_settings['MEDIA_ROOT'] = self.temp_media_root
        elif storage_cls != 'storages.backends.s3boto3.S3Boto3Storage':
            raise Exception("Unsupported DEFAULT_FILE_STORAGE %s" % storage_cls)
        self.override = override_settings(**new_settings)
        self.override.enable()

    def _post_teardown(self):
        if hasattr(default_storage, 'bucket'):
            default_storage.bucket.objects.filter(Prefix=default_storage.location).delete()
        else:
            shutil.rmtree(self.temp_media_root)

        self.override.disable()

        super(CropdusterTestCaseMediaMixin, self)._post_teardown()

    def setUp(self):
        super(CropdusterTestCaseMediaMixin, self).setUp()

        random = uuid.uuid4().hex
        self.TEST_IMG_DIR = ORIG_IMG_PATH
        self.TEST_IMG_DIR_RELATIVE = os.path.join(random, 'data')

    def create_unique_image(self, image):
        image_uuid = uuid.uuid4().hex

        ext = os.path.splitext(image)[1]
        image_name = os.path.join(
            self.TEST_IMG_DIR_RELATIVE, image_uuid, "original%s" % ext)

        with open("%s/%s" % (ORIG_IMG_PATH, image), mode='rb') as f:
            default_storage.save(image_name, ContentFile(f.read()))

        return image_name
