import os
import shutil
import uuid

from django.conf import settings

PATH = os.path.split(__file__)[0]
ORIG_IMG_PATH = os.path.join(PATH, 'data')


class CropdusterTestCaseMediaMixin(object):

    def setUp(self):
        super(CropdusterTestCaseMediaMixin, self).setUp()

        random = uuid.uuid4().hex
        self.TEST_IMG_ROOT = os.path.join(settings.MEDIA_ROOT, random)
        self.TEST_IMG_DIR = os.path.join(self.TEST_IMG_ROOT, 'data')
        self.TEST_IMG_DIR_RELATIVE = os.path.join(random, 'data')

        # Create directory for test images
        shutil.copytree(ORIG_IMG_PATH, self.TEST_IMG_DIR)

    def tearDown(self):
        super(CropdusterTestCaseMediaMixin, self).tearDown()

        # Remove all generated images
        shutil.rmtree(self.TEST_IMG_ROOT, ignore_errors=True)

    def create_unique_image(self, image):
        image_uuid = uuid.uuid4().hex
        image_dir = os.path.join(self.TEST_IMG_DIR, image_uuid)

        if not os.path.exists(image_dir):
            os.makedirs(image_dir)

        ext = os.path.splitext(image)[1]
        image_name = os.path.join(
            self.TEST_IMG_DIR_RELATIVE, image_uuid, "original%s" % ext)

        shutil.copyfile(
            os.path.join(self.TEST_IMG_DIR, image),
            os.path.join(settings.MEDIA_ROOT, image_name))
        return image_name
