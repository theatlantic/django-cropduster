#Place in cropduster/management/commands/regenerate_thumbs.py.
# Afterwards, the command can be run using:
# manage.py regenerate_thumbs
#
# Search for 'changeme' for lines that should be modified

import os
import inspect
from optparse import make_option

from django.db.models.base import ModelBase
from django.core.management.base import BaseCommand, CommandError

from cropduster.models import Image as CropDusterImage, Thumb as CropDusterThumb
from cropduster.utils import create_cropped_image, rescale
import Image

def generate_and_save_thumbs(db_image, sizes, img, file_dir, file_ext, is_auto=False):
    '''
    Loops through the sizes given and saves a thumbnail for each one. Returns
    a dict of key value pairs with size_name, thumbnail_id
    '''
    thumb_ids = {}

    img_save_params = {}
    if img.format == 'JPEG':
        img_save_params['quality'] = 95

    for size_name in sizes:
        size = sizes[size_name]
        thumb_w = int(size[0])
        thumb_h = int(size[1])

        thumb = img.copy()
        if is_auto:
            thumb = rescale(img, thumb_w, thumb_h)
        else:
            thumb = rescale(thumb, thumb_w, thumb_h, crop=False)

        # Save to the real thumb_path if the image is new

        thumb_path = file_dir + '/' + size_name + file_ext
        if not os.path.exists(thumb_path):
            thumb.save(thumb_path, **img_save_params)

        thumb_tmp_path = file_dir + '/' + size_name + '_tmp' + file_ext

        thumb.save(thumb_tmp_path, **img_save_params)

        db_thumb = db_image.save_thumb(
            width = thumb_w,
            height = thumb_h,
            name = size_name
        )
        thumb_ids[size_name] = db_thumb.id

    return thumb_ids

def to_CE(f, *args, **kwargs):
    """
    Simply re-raises any error as a CommandError.
    
    @param f: function to call
    @type  f: callable(f) 

    @return: f(*args, **kwargs)
    @rtype: object
    """
    try:
        return f(*args, **kwargs)
    except Exception, e:
        raise CommandError('Error: %s(%s)' % (type(e), e))
 
class PrettyError(f):
    def __init__(self, msg):
        self.msg = msg

    def __call__(self, f):
        def _f(*args, **kwargs):
            try:
                return f(*args, **kwargs)
            except Exception:
                raise CommandError(self.msg % dict(error=e))
    return _f

class Command(BaseCommand):
    args = "app_name[:model[.field]][, ...]"
    help = "Regenerates cropduster thumbnails for an entire "\
           "app or specific model and/or field."

    option_list = BaseCommand.option_list + (
        make_option('--verify',
                    action  = "store_true",
                    dest    = "verify",
                    default = False,
                    help    = "Checks that all the thumbs are generated for an app."),

        make_option('--force',
                    action  = "store_true",
                    dest    = "force",
                    default = False,
                    help    = "Resizes all images regardless of whether or not they already exist"),

        make_option('--query_set',
                    dest="query_set",
                    default="all()",
                    help="Queryset to use.  Default uses all models.")
    )
    
    # Returns the path where an object was defined.
    get_def_file = lambda s, o: os.path.abspath(inspect.getfile(o))

    def find_django_models(self, module):
        """
        Returns all django models defined within a module.  It attempts this
        by iterating through the module's contents and finding subclasses
        of the Django base model.

        @param module: Python Module
        @type  module: Python Module

        @return: Set of Django Model Classes
        @rtype: [Class1, ...]
        """
        cur_file = self.get_def_file(module)
        classes = []
        for obj in module.__dict__.itervalues():
            # We check the definition file for each object to make sure we
            # only grab local models, not imports.
            if isinstance(obj, ModelBase) and cur_file == self.get_def_file(obj):
                classes.append(obj)

        return classes

    def find_cropduster_images(self, model):
        """
        Dives into a model to find Cropduster images.

        TODO:  Find if there's a cleaner way to do this.

        @param model: Model to introspect. 
        @type  model: Class 

        @return: Set of cropduster image fields.
        @rtype:  ["field1", ...]
        """
        fields = []
        for field_name, dets in model._meta._name_map.iteritems():
            if isinstance(dets[0], Image):
                fields.append(field_name)
        return field

    def import_app(self, app_name, model_name=None, field_name=None):
        """
        Imports an app and figures out which models and fields are Cropduster 
        Images

        @param app_name: Name of the app, as known by its path
        @type  app_name: "name" 
        
        @param model_name: Specific model to use or None to look at all models.
        @type  model_name: "Model Name" or None
        
        @param field_name: Specific field on a model or None to look at all 
                           fields. 
        @type  field_name: "field name" or None

        @return: set of field names by model
        @rtype: [(Model1, ["field1", ...])]
        """
        # Attempt to import
        module = to_CE(__import__, appname + '.models', globals(), locals())

        # if we have a specific model, use only that particular one.
        if model_name is not None:
            models = [ to_CE(getattr, module, model_name) ]

        else:
            # Attempt to introspect the module
            models = self.find_django_models(module)

        # Find all the relevant field(s)
        if field_name is not None:
            field_map = [(models[0], [ to_CE(getattr, models[0], field_name) ])]
        else:
            # Otherwise, more introsepction!
            field_map = []
            for model in models:
                field_map.append((model, self.find_cropduster_images(model)))

        return field_map

    @PrettyError("Failed to regenerate thumbs: %(error)s")
    def handle(self, paths, **options):
        pass
        
    @PrettyError("Failed to regenerate thumbs: %(error)s")
    def handle(self, *args, **options):
        print args, options
        num_resized = num_tried = num_thumbs = 0

        # changeme
        #videos = Entry.objects.all()
        for video in videos:
            db_image = video.image
            if db_image is None:
                continue
            # changeme
            sizes = {
                "still": (620, 465),
                "thumb": (120, 90),
            }
            (width, height) = video.get_video_dimensions()
            if width is not None and height is not None:
                if width > 620:
                    still_width = 620
                    still_height = int(round(620 * height / width))
                else:
                    still_width = int(width)
                    still_height = int(height)
                thumb_height = int(round(120 * height / width))
                # changeme
                sizes = {
                    "still": (still_width, still_height),
                    "thumb": (120, thumb_height),
                }
            
            num_tried += 1
            try:
                original_file_path = db_image.get_image_path("original")
                img = Image.open(original_file_path)

                (w, h) = img.size
                # First pass resize if it's too large
                # (height > 500 px or width > 800 px)
                resize_ratio = min(800/float(w), 500/float(h))
                if resize_ratio < 1:
                    w = int(round(w * resize_ratio))
                    h = int(round(h * resize_ratio))
                    img.thumbnail((w, h), Image.ANTIALIAS)
            
                preview_file_path = db_image.get_image_path("_preview")
                img_save_params = {}
                if img.format == 'JPEG':
                    img_save_params['quality'] = 95
                img.save(preview_file_path, **img_save_params)
                num_resized += 1
                num_thumbs += 1
                file_root, file_ext = os.path.splitext(original_file_path)
                file_dir, file_prefix = os.path.split(file_root)
                auto_sizes = {
                    'atlantic_thumb': (110, 90),
                    'grid': (130, 100),
                    'related': (88,66),
                }
                cropped_img = create_cropped_image(original_file_path, x=db_image.crop_x, y=db_image.crop_y, w=db_image.crop_w, h=db_image.crop_h)
                generate_and_save_thumbs(db_image, sizes, cropped_img, file_dir, file_ext, is_auto=False)
                generate_and_save_thumbs(db_image, auto_sizes, cropped_img, file_dir, file_ext, is_auto=True)
                db_image.save()
            except Exception, e:
                self.stdout.write("Encountered error on %s: %s\n" % (db_image.path, unicode(e)))
        
        self.stdout.write("Successfully resized %d of %d thumbnails (%d)\n" % (num_resized, num_tried, num_thumbs))
