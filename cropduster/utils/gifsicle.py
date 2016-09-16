import logging
import os
import tempfile
import subprocess

from cropduster.settings import CROPDUSTER_GIFSICLE_PATH


logger = logging.getLogger(__name__)


class GifsicleImage(object):

    def __init__(self, im):
        if not CROPDUSTER_GIFSICLE_PATH:
            raise Exception(
                "Cannot use GifsicleImage without the gifsicle binary in the PATH")

        self.pil_image = im
        self.size = im.size

        filename = getattr(im, 'filename', None)
        if not filename or not os.path.exists(filename):
            temp_file = tempfile.NamedTemporaryFile(suffix='.gif')
            filename = temp_file.name
            im.save(filename)

        self._filename = filename

        self.cmd_args = [CROPDUSTER_GIFSICLE_PATH, '-O3', '-I', '-I', '-w']
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

    def save(self, output_filename, **kwargs):
        args = self.args + ['-o', output_filename, self._filename]
        proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = proc.communicate()
        logger.debug(err)
