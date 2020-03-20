import logging
import os
import tempfile
import subprocess

from io import BytesIO
from cropduster.settings import CROPDUSTER_GIFSICLE_PATH
from PIL import ImageSequence


logger = logging.getLogger(__name__)


class GifsicleImage(object):

    def __init__(self, im):
        if not CROPDUSTER_GIFSICLE_PATH:
            raise Exception(
                "Cannot use GifsicleImage without the gifsicle binary in the PATH")

        self.pil_image = im
        self.size = im.size

        buf = BytesIO()
        # pass list of durations to set the duration for each frame separately
        duration = [frame.info['duration'] for frame in ImageSequence.Iterator(im)]
        im.info['duration'] = duration
        im.save(buf, save_all=True, format=im.format, duration=duration)
        self.src_bytes = buf.getvalue()
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

    def save(self, buf, **kwargs):
        proc = subprocess.Popen(self.args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = proc.communicate(input=self.src_bytes)
        logger.debug(err)
        buf.write(out)
        buf.seek(0)
