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
