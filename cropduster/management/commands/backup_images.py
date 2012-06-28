#Place in cropduster/management/commands/regenerate_thumbs.py.
# Afterwards, the command can be run using:
# manage.py regenerate_thumbs
#
# Search for 'changeme' for lines that should be modified

import sys
import os
import tempfile
from optparse import make_option

from django.core.management.base import BaseCommand, CommandError

from cropduster.models import Image as CropDusterImage,CropDusterField as CDF
from cropduster.utils import create_cropped_image, rescale
import apputils
import Image

class Command(BaseCommand):
    args = "app1 [app2...]"
    help = "Backs up all images for an app in cropduster."

    option_list = BaseCommand.option_list + (
        make_option('--only_originals',
                    action="store_true",
                    dest='only_origs',
                    help="Indicates whether or not to include derived thumbnails. If provided, will exclude all derived images.  This would make it necessary to run regenerate_thumbs."),
        make_option('--query_set',
                    dest    = "query_set",
                    default = "all()",
                    help    = "Queryset to use.  Default uses all().  This option makes it possible to do iterative backups"),
        
        make_option('--backup_file',
                    dest="backup_file",
                    default="cropduster.bak.tar",
                    help = "TarFile location to store backup")
    )
    
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

    def get_derived_paths(self, cd_image):
        """
        Gets the derived image paths.

        @param cd_image: Cropduster image to use
        @type  cd_image: CropDusterImage

        @return: Set of paths
        @rtype:  Sizes
        """
        sizes = []
        for size in cd_image.size_set.size_set.all():
            path = cd_image.thumbnail_path(size)
            if os.path.exists(path):
                yield path

    def find_image_files(self, apps, query_set, only_originals):
        """
        Finds all images specified in apps and builds a list of paths that
        need to be stored.

        @param apps: Set of app paths to look for images in.
        @type  apps: ["app[:model[.field]], ...]
        
        @param query_set: Query set of models to backup.
        @type  query_set: str 
        
        @param only_originals: Whether or not to only backup originals.
        @type  only_originals: bool

        """
        # Figures out the models and cropduster fields on them
        for model, field_names in apputils.resolve_apps(apps):

            # Returns the queryset for each model
            query = self.get_queryset(model, query_set)
            for obj in query:

                for field_name in field_names:

                    # Sanity check; we really should have a cropduster image here.
                    cd_image = getattr(obj, field_name)
                    if not (cd_image and isinstance(cd_image, CropDusterImage)):
                        continue

                    # Make sure the image actually exists.
                    file_name = cd_image.image.path
                    if not os.path.exists(file_name):
                        sys.stderr.write('missing: %s\n' % file_name)
                        continue

                    yield file_name
                    if only_originals:
                        continue
                    
                    # Get all derived images as well
                    for path in self.get_derived_paths(cd_image):
                        yield path

    #@PrettyError("Failed to build thumbs: %(error)s")
    def handle(self, *apps, **options):
        """
        Grabs all images for a given app and stores them in a tar file.
        """
        abs_path = os.path.abspath( options['backup_file'] )
        if os.path.exists(abs_path):
            print "\nBackup file `%s` already exists.  If you continue, the file "\
                  "will be overwritten." % options['backup_file']
            ret = raw_input('Continue? [y/N]: ')
            if not ret.lower() == 'y':
                raise SystemExit('Quitting...')

        file_list_path = abs_path + '.files'
        
        print "Finding image files..."
        # find all images
        with file(file_list_path, 'w') as file_list:
            for i, path in enumerate(self.find_image_files(apps,
                                               options['query_set'],
                                               options['only_origs'])):
                file_list.write( (path+'\n').encode('utf8') )
            
            print "Found %i images to archive" % (locals().get('i', -1) + 1)

        # attempt to tar 
        print "Tarring...."
        ret_code = os.system('tar cvf %s.tmp -T %s' % (abs_path, file_list_path)) >> 8
        if ret_code > 0:
            raise CommandError("Failed when tarring files!  Exit code: %i" % ret_code)
            
        # Success!
        os.remove(file_list_path)
        os.rename(abs_path+'.tmp', abs_path)
        print "Successfully tarred images to %s" % abs_path
