import sys
import os
import logging
import traceback
from optparse import make_option

try:
    from PIL import Image
except ImportError:
    import Image

from django.core.management.base import BaseCommand, CommandError

from cropduster3.models import Image as CropDusterImage
from cropduster3.utils import rescale, create_cropped_image, normalize_dimensions

from .apputils import resolve_apps


class handle_error(object):

    def __init__(self, msg):
        self.msg = msg

    def __call__(self, f):
        def _f(*args, **kwargs):
            try:
                return f(*args, **kwargs)
            except CommandError:
                raise
            except Exception, e:
                sys.stderr.write(traceback.format_exc(e))
                raise CommandError(self.msg % dict(error=e))

        return _f


class Command(BaseCommand):

    args = "app_name[:model[.field]][, ...]"

    help = "Regenerates cropduster thumbnails for an entire "\
           "app or specific model and/or field."

    option_list = BaseCommand.option_list + (
        make_option('--force',
                    action="store_true",
                    dest="force",
                    default=False,
                    help="Resizes all images regardless of whether or not "
                         "they already exist."),
        make_option('--queryset',
                    dest="queryset",
                    default="all()",
                    help="Queryset to use. Default uses all models."),
        make_option('--stretch',
                    dest='stretch',
                    action="store_true",
                    default=False,
                    help="Indicates whether to resize an image if size is larger "
                         "than original. Default is False."),
        make_option('--log_file',
                    dest='logfile',
                    default='regen_thumbs.out',
                    help="Location of the log file. Default regen_thumbs.out"),

        make_option('--log_level',
                    dest='loglevel',
                    default='INFO',
                    help="One of ERROR, INFO, DEBUG. Default is INFO"),
        make_option('--stdout',
                    dest='stdout',
                    action="store_true",
                    default=False,
                    help="Prints log messages to stdout as well as log. Default False"),
        make_option('--processes',
                    dest='procs',
                    type="int",
                    default=1,
                    help="Indicates how many procs to use for converting images. "
                         "Default is 1"),
    )

    IMG_TYPE_PARAMS = {
        'JPEG': {'quality': 90, 'optimize': 1},
    }

    def get_queryset(self, model, query_str):
        """
        Gets the query set from the provided model based on the user's filters.

        @param model: Django Model to query
        @type  model: Class

        @param query_str: Filter query to retrieve objects with
        @type  query_str: "filter string"

        @return: QuerySet for the given model.
        @rtype:  <iterable of object>
        """
        query_str = 'model.objects.' + query_str.lstrip('.')
        return eval(query_str, dict(model=model))

    def get_sizes(self, cd_image, stretch):
        """
        Extracts sizes for an image.

        @param cd_image: Cropduster image to use
        @type  cd_image: CropDusterImage

        @param stretch: Indicates whether or not we want to include sizes that
                        would stretch the original image.
        @type  stretch: bool

        @return: Set of sizes to use
        @rtype:  set([Size, ...])
        """
        sizes = []

        # Doubles a variable, but only if it supports the multiply operation
        safe_double = lambda n: n * 2 if hasattr(n, '__mul__') else n

        def all_images(orig_image):
            orig_width, orig_height = orig_image.image.width, orig_image.image.height
            for derived_image in orig_image.derived.all():
                img_size = derived_image.size
                if not stretch and (orig_width < img_size.width or orig_height < img_size.height):
                    continue
                size = {
                    'orig_path': orig_image.get_dest_img_path(),
                    'path': derived_image.get_dest_img_path(),
                    'orig_w': orig_width,
                    'orig_h': orig_height,
                    'slug': img_size.slug,
                    'width': img_size.width,
                    'height': img_size.height,
                    'auto_crop': img_size.auto_crop,
                }
                crop = {
                    'x': derived_image.crop.crop_x,
                    'y': derived_image.crop.crop_y,
                    'w': derived_image.crop.crop_w,
                    'h': derived_image.crop.crop_h,
                }
                yield derived_image, size, crop

                if derived_image.size.retina:
                    retina_size = size.copy()
                    retina_size['width'] = safe_double(retina_size['width'])
                    retina_size['height'] = safe_double(retina_size['height'])
                    retina_size['path'] = derived_image.retina_path
                    retina_size['slug'] += '@2x'
                    if not stretch and (orig_width < retina_size['width'] or orig_height < retina_size['height']):
                        continue
                    yield derived_image, retina_size, crop

        image_iter = all_images(cd_image)
        for derived_image, size, crop in image_iter:
            sizes.append((size, crop))
        return sizes

    def setup_logging(self, options):
        """
        Sets up logging details.
        """
        logging.basicConfig(filename=options['logfile'],
                            level=getattr(logging, options['loglevel'].upper()),
                            format="%(asctime)s %(levelname)s %(message)s")

        # Add stdout to logging, useful for short query sets.
        if 'stdout' in options:
            formatter = logging.root.handlers[0].formatter
            sh = logging.StreamHandler(sys.stdout)
            sh.formatter = formatter
            logging.root.addHandler(sh)

    def get_images(self, apps, queryset, stretch):
        """
        Returns all original images and sizes for the given apps and query sets.

        @param apps: Set of django apps to resize.
        @type  apps: ["app:[model[.field]]", ..]

        @param queryset: queryset to retrieve objects with.
        @type  queryset: str.

        @param stretch: Whether or not to include sizes with dimensions larger
                        than the original image size.
        @type  stretch: bool

        @return: Generator yielding the raw Image and its sizes
        @rtype: < (PIL.Image, [set([Size1, ...])), ... >
        """
        # Figures out the models and cropduster fields on them
        for model, field_names in resolve_apps(apps):
            logging.info("Processing model %s with fields %s" % (model, field_names))

            # Returns the queryset for each model
            query = self.get_queryset(model, queryset)

            logging.info("Queryset return %i objects" % query.count())

            for obj in query:
                for field_name in field_names:
                    # Sanity check; we really should have a cropduster image here.
                    cd_image = getattr(obj, field_name)
                    if not (cd_image and isinstance(cd_image, CropDusterImage)):
                        continue

                    file_name = cd_image.image.path
                    logging.info("Processing image %s" % file_name)
                    try:
                        image = Image.open(file_name)
                    except IOError:
                        logging.warning('Could not open image %s' % file_name)
                        continue

                    sizes = self.get_sizes(cd_image, stretch)
                    yield image, sizes

    def wait_all(self):
        """
        Wait for all child procs to finish.
        """
        while True:
            try:
                os.wait()
            except OSError, e:
                # Excellent, no longer waiting on a child proc
                if e.errno == 10:
                    return
                raise

    def wait_one(self, proc_list):
        """
        Waits for any process to finish. If any child terminated
        abnormally, raise an OSError.

        @param proc_list: Set of child procs.
        @type  proc_list: set(int, ...)
        """
        pid, code = os.wait()
        proc_list.remove(pid)
        # If an error
        if code > 0:
            self.wait_all(proc_list)
            raise OSError('Process %i died with %i' % (pid, code))

    def resize_parallel(self, images, force, total_procs):
        """
        Resizes images in parallel.

        Why not use multiprocessing?  First reason is that we don't care
        about return values, which makes the synchronization for Pool objects
        more than we need.

        Secondly, Process() has issues with KeyboardInterrupt exceptions,
        which is a bummer when testing. Further, we never know which Process
        finishes first without using os.wait, which at that point we have
        what we have below. The other option would be to loop through each
        process, calling its join() method with a timeout, which  basically
        turns the parent process into a spin lock.

        Thirdly, we want to throw away our process when we are done with each
        image. Forking is cheap due to copy-on-write, and this keeps the
        memory consumption down.

        @param images: Iterator yield images with their size set.
        @type  images: ((image, sizes), ...]

        @param force: Whether or not resize images which already exist.
        @type  force: bool

        @param total_procs: Total number of processes to use.
        @type  total_procs: positive int
        """
        proc_list = set()
        try:
            for image, size in images:
                if len(proc_list) == total_procs:
                    self.wait_one(proc_list)

                pid = os.fork()
                if pid:
                    proc_list.add(pid)
                    continue

                # The child carries on
                try:
                    self.resize_image(image, size, force)
                except:
                    # Any error, doesn't matter what, must get caught.
                    os._exit(1)
                os._exit(0)
        finally:
            # wait for the kids to finish, no zombies for us.
            self.wait_all()

    def resize_image(self, image, sizes, force):
        """
        Resizes an image to the provided set sizes.

        @param image: Opened original image
        @type  image: PIL.Image

        @param sizes: Set of sizes to create.
        @type  sizes: [Size1, ...]

        @param force: Whether or not to recreate a thumbnail if it already exists.
        @type  force: bool
        """
        for size, crop in sizes:
            img_params = (self.IMG_TYPE_PARAMS.get(image.format) or {}).copy()
            dst_width, dst_height = normalize_dimensions(image, (size['width'], size['height']))
            logging.debug("Converting image to size `%(slug)s` (%(w)s x %(h)s)" % {
                'slug': size['slug'],
                'w': dst_width,
                'h': dst_height,
            })
            if (dst_width * dst_height) > 160000 and img_params.get('quality'):
                img_params['quality'] = 85
            if not force and os.path.isfile(size['path']) and os.stat(size['path']).st_size > 0:
                logging.debug(' - Image `%s` exists, skipping...' % size['slug'])
                continue

            folder, _ = os.path.split(size['path'])
            if not os.path.isdir(folder):
                logging.debug(' - Directory %s does not exist. Creating...' % folder)
                os.makedirs(folder)

            tmp_path = '%s.tmp' % size['path']
            try:
                # In place scaling, so we need to use a copy of the image.
                if size['auto_crop']:
                    new_image = image.copy()
                else:
                    new_image = create_cropped_image(image.filename, **crop)
                thumbnail = rescale(new_image, size['width'], size['height'], crop=size['auto_crop'])
                thumbnail.save(tmp_path, image.format, **img_params)
            # No idea what this can throw, so catch them all
            except Exception, e:
                logging.exception('Error saving thumbnail to %s: %s' % (tmp_path, e))
                raise SystemExit('Exiting...')
            else:
                os.rename(tmp_path, size['path'])

    @handle_error("Failed to regenerate thumbs: %(error)s")
    def handle(self, *apps, **options):
        """
        Resolves out the models and images for regeneratating thumbnails and
        then resolves them.
        """
        self.setup_logging(options)

        # Get all images
        images = self.get_images(apps, options['queryset'], options['stretch'])

        # Go to town on the images.
        if options['procs'] > 1:
            self.resize_parallel(images, options['force'], options['procs'])
        else:
            for image, size in images:
                self.resize_image(image, size, options['force'])
