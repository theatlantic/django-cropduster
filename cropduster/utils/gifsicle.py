import logging
import subprocess

from cropduster.conf import settings as cropduster_settings

from .storage import get_image_storage


logger = logging.getLogger(__name__)


class GifsicleImage(object):

    def __init__(self, im, storage=None):
        gifsicle_path = cropduster_settings.CROPDUSTER_GIFSICLE_PATH
        if not gifsicle_path:
            raise Exception(
                "Cannot use GifsicleImage without the gifsicle binary in the PATH")

        self.storage = storage or get_image_storage()
        self.pil_image = im
        self.size = im.size
        self.cmd_args = [gifsicle_path, '-O3', '-I', '-I', '-w']
        self.crop_args = []
        self.resize_args = []

    @property
    def args(self):
        return self.cmd_args + self.crop_args + self.resize_args

    def crop(self, box):
        x1, y1, x2, y2 = box
        if x2 < x1:
            x2 = x1
        if y2 < y1:
            y2 = y1

        self.size = (x2 - x1, y2 - y1)
        self.crop_args = ['--crop', "%d,%d-%d,%d" % (x1, y1, x2, y2)]
        return self

    def resize(self, size, method):
        # Ignore method, PIL's algorithms don't match up
        self.resize_args = [
            "--resize-fit", "%dx%d" % size,
            "--resize-method", "mix",
            "--resize-colors", "128",
        ]
        return self

    def save(self, buf, **kwargs):
        proc = subprocess.Popen(self.args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        with self.storage.open(self.pil_image.filename, 'rb') as f:
            out, err = proc.communicate(input=f.read())
        logger.debug(err)
        buf.write(out)
        buf.seek(0)
