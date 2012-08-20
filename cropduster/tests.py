import datetime
import unittest
import os
import hashlib
import shutil
import uuid

from django.conf import settings
PATH = os.path.split(__file__)[0]

from django.db import models
from django.core.files.base import ContentFile
from django.core.exceptions import ObjectDoesNotExist as DNE, ValidationError
import cropduster.models as CM

from PIL import Image

abspath = lambda x: os.path.join(PATH, x)
to_retina_path = lambda p: '%s@2x%s' % os.path.splitext(p)

def save_all(objs):
    for o in objs:
        o.save()

def delete_all(model):
    for o in model.objects.all():
        o.delete()

def hashfile(path):
    md5 = hashlib.md5()
    with file(path) as f:
        data = f.read(4096)
        while data:
            md5.update(data)
            data = f.read(4096)

    return md5.digest()

settings.MEDIA_ROOT = settings.STATIC_ROOT = settings.UPLOAD_PATH = '/tmp/cd_test/%s' % uuid.uuid4().hex
ORIG_IMAGE = abspath('testdata/img1.jpg')
TEST_IMAGE = settings.UPLOAD_PATH + '/' + os.path.basename(ORIG_IMAGE)
class TestCropduster(unittest.TestCase):
    def setUp(self):
        os.makedirs(settings.MEDIA_ROOT)
        settings.CROPDUSTER_UPLOAD_PATH = 'cd'
        os.system('cp %s %s' % (ORIG_IMAGE, TEST_IMAGE))
        # Backup the image

    def tearDown(self):
        # Delete all objects
        delete_all( CM.Image )
        delete_all( CM.SizeSet )
        delete_all( CM.Size )
        delete_all( CM.Crop )

        if os.path.exists(settings.UPLOAD_PATH):
            os.system('rm -rf %s' % settings.UPLOAD_PATH)

    def create_size_sets(self):
        iss = CM.SizeSet(name='Facebook', slug='facebook')
        iss.save()

        thumb = CM.Size(name='Thumbnail',
                             slug='thumb',
                             width=60,
                             height=60,
                             auto_crop=True,
                             retina=True,
                             size_set=iss)
        thumb.save()

        banner = CM.Size(name='Banner',
                              slug='banner',
                              width=1024,
                              aspect_ratio=1.3,
                              size_set=iss)
                                
        banner.save()

        iss2 = CM.SizeSet(name='Mobile', slug='mobile')
        iss2.save()

        splash = CM.Size(name='Headline',
                              slug='headline',
                              width=500,
                              height=400,
                              retina=True,
                              auto_crop=True,
                              size_set=iss2)

        splash.save()

    def get_test_image(self, image=TEST_IMAGE):
        cd1 = CM.Image(image=image)
        cd1.metadata.attribution = "AP",
        cd1.metadata.caption = 'This is a galaxy'
        cd1.save()
        return cd1

    def test_original(self):
        cd1 = self.get_test_image()
        self.assertEquals(cd1.is_original, True)
        self.assertEquals(cd1.derived.count(), 0)

    def test_size_sets(self):   
        """
        Tests size sets work correctly on images.
        """
        cd1 = self.get_test_image()

        self.create_size_sets()

        # Add the size set
        child_images = cd1.add_size_set(name='Facebook')

        # Check that we now have two derived images which haven't been rendered.
        self.assertEquals(len(child_images), 2)
        self.assert_(all(not ci.image for ci in child_images))

        # Should be zero since we haven't saved the images
        self.assertEquals(cd1.derived.count(), 0)

        save_all(child_images)

        self.assertEquals(cd1.derived.count(), 2)

        # Try adding it again, which should basically do a no-op
        images = cd1.add_size_set(name='Facebook')
        
        # No new image sizes added, so no more images.
        self.assertEquals(len(images), 0)

        self.assertEquals(cd1.size_sets.count(), 1)

        # Try adding one that doesn't exist
        self.failUnlessRaises(DNE, cd1.add_size_set, name='foobar')

        # Add another new size_set
        new_images = cd1.add_size_set(slug='mobile')
        self.assertEquals(len(new_images), 1)

        save_all(new_images)

        self.assertEquals(cd1.derived.count(), 3)

    def test_render_original(self):
        """
        Tests that we can render the original image.
        """
        cd1 = self.get_test_image()
        size = CM.Size(name='test', slug='test', width=50,
                            height=50, auto_crop=True, retina=False)
        size.save()
        cd1.size = size

        # Check that we are protecting original images.
        self.failUnlessRaises(ValidationError, cd1.render)

        # Get hash of original
        orig_hash = hashfile( cd1.image.path )
        cd1.render(force=True)

        # Check that it hasn't overwritten the original file until we save.
        self.assertEquals( hashfile(cd1.image.path), orig_hash)

        cd1.save()

        # Check that it changed.
        self.assertNotEquals(orig_hash, hashfile( cd1.image.path ) )

    def test_render_derived(self):
        """
        Tests that we can correctly render derived images from the original.
        """
        self.create_size_sets()

        cd1 = self.get_test_image()
        image = cd1.add_size_set(slug='mobile')[0]

        image.render()
        image.save()

        size = image.size
        self.assertEquals(image.width, size.width)
        self.assertEquals(image.height, size.height)
        self.assertNotEquals(image.original.image.path, 
                             image.image.path)

        # Check that files are not the same
        new_image_hash = hashfile(image.image.path)
        self.assertNotEquals(
            hashfile( image.original.image.path ),
            new_image_hash
        )

        # Change the original image, and check that the derived image
        # also changes when re-rendered.
        cd1.size = CM.Size.objects.get(slug='thumb')
        cd1.render(force=True)
        cd1.save()

        image.render()
        image.save()

        self.assertNotEquals(
            hashfile(image.image.path),
            new_image_hash
        )

        # Check that the images are relative
        self.assert_(not os.path.isabs(cd1.image.name))

    def test_delete(self):
        """
        Tests that deletion cascades from the root to all derived images.
        """
        self.create_size_sets()

        cd1 = self.get_test_image()

        for image in cd1.add_size_set(slug='facebook'):
            image.render()
            image.save()

        for image in image.add_size_set(slug='facebook'):
            image.render()
            image.save()

        self.assertEquals(CM.Image.objects.count(), 5)

        cd1.delete()

        self.assertEquals(CM.Image.objects.count(), 0)

    def test_multi_level_delete(self):
        """
        Creates a multi-level tree from one image and deletes it.
        """
        self.create_size_sets()
        cd1 = self.get_test_image()

        stack = [cd1]
        for i,image in enumerate(stack):
            for size_set in CM.SizeSet.objects.all():
                for new_image in image.add_size_set(size_set):
                    new_image.render()
                    new_image.save()
                    stack.append(new_image)
            if i > 20:
                break

        # We should have a lot of images.
        self.assertEquals(CM.Image.objects.count(), len(stack))

        cd1.delete()

        self.assertEquals(CM.Image.objects.count(), 0)

    def test_manual_derive(self):
        """
        Tests that we can do one-off derived images.
        """
        self.create_size_sets()
        cd1 = self.get_test_image()

        img = cd1.new_derived_image()

        size = CM.Size.objects.create(slug='testing',
                                           width=100,
                                           height=100,
                                           auto_crop=True,
                                           retina=True)

        # Test the manual size exists
        self.assertEquals(CM.Size.objects.count(), 4)

        self.assertEquals( cd1.has_size('testing'), False )
        img.size = size

        # Check that the crop is deleted as well
        img.set_crop(0, 0, 200, 200).save()
        self.assertEquals(CM.Crop.objects.count(), 1)

        img.render()
        img.save()

        self.assertEquals( cd1.has_size('testing'), True )

        self.assertEquals(img.width, 100)
        self.assertEquals(img.height, 100)

        # Test that the manual size is deleted with the image.
        img.delete()

        self.assertEquals(CM.Size.objects.count(), 3)
        self.assertEquals(CM.Size.objects.filter(pk=size.id).count(), 0)
        self.assertEquals(CM.Crop.objects.count(), 0)

        # No more derived images.
        self.assertEquals(cd1.derived.count(), 0)

    def test_crop(self):
        cd1 = self.get_test_image()

        img = cd1.new_derived_image()
        img.set_crop(100,100,300,300).save()

        img.render()
        img.save()

        self.assertEquals(img.width, 300)
        self.assertEquals(img.height, 300)

    def test_no_modify_original(self):
        """
        Makes sure that a derived image cannot overwrite an original.
        """
        cd1 = self.get_test_image()

        orig_hash = hashfile(cd1.image.path)

        img = cd1.new_derived_image()

        img.set_crop(100, 100, 300, 300).save()

        img.render()
        img.save()

        self.assertEquals(orig_hash, hashfile(cd1.image.path))
        self.assertNotEquals(orig_hash, hashfile(img.image.path))

    def test_calc_sizes(self):
        """
        Tests that omitted dimension details are correctly calculated.
        """

        size = CM.Size(slug='1', width=100, aspect_ratio=1.6)
        self.assertEquals(size.get_height(), round(100/1.6))

        size2 = CM.Size(slug='2', height=100, aspect_ratio=2)
        self.assertEquals(size2.get_width(), 200)

        size3 = CM.Size(slug='3', height=3, width=4)
        self.assertEquals(size3.get_aspect_ratio(), 1.33)

    def test_variable_sizes(self):
        """
        Tests that variable sizes work correctly.
        """
        cd1 = self.get_test_image()

        img = cd1.new_derived_image()
        size = CM.Size(slug='variable', width=100, aspect_ratio=1.6)
        size.save()

        img.size = size
        img.render()
        img.save()

        self.assertEquals(size.get_height(), img.height)

        # Only width or only height
        size = CM.Size(slug='width_only', width=100)
        img.size = size
        img.render()
        img.save()

        self.assertEquals(img.width, 100)
        self.assertEquals(int(round(100/cd1.aspect_ratio)), img.height)
        self.assertEquals(cd1.aspect_ratio, img.aspect_ratio)

        size = CM.Size(slug='height_only', height=100)
        img.size = size
        img.render()
        img.save()

        self.assertEquals(img.height, 100)
        self.assertEquals(int(round(100 * cd1.aspect_ratio)), img.width)
        self.assertEquals(cd1.aspect_ratio, img.aspect_ratio)

    def _test_delete_images(self):
        """
        Check that all image files are correctly deleted.  Commented out since
        right now we don't really care about it.
        """
        self.create_size_sets()
        cd1 = self.get_test_image()

        paths = []
        for image in cd1.add_size_set(slug='facebook'):
            image.render()
            image.save()
            paths.append(image.image.path)

        # Check that the paths are unique
        self.assertEquals(len(paths), len(set(paths)))
        for path in paths:
            self.assert_(os.path.exists(path), "Image at %s does not exist!" % path)

        cd1.delete()

        for path in paths:
            self.assert_(not os.path.exists(path), "Image at %s was not deleted!" % path)

    def test_retina_image(self):
        """
        Tests that retina images are properly rendered when they can be.
        """
        cd1 = self.get_test_image()

        size1 = CM.Size(slug='thumbnail',
                             width=128,
                             height=128,
                             retina=True)
        size1.save()

        img1 = cd1.new_derived_image()
        img1.size = size1

        img1.render()
        img1.save()

        # Retina images can't be handled directly, they only give a path.
        self.assertEquals(img1.retina_path, 
                          to_retina_path(img1.image.path))

        retina = Image.open(img1.retina_path)
        self.assertEquals(retina.size, (img1.width*2, img1.height*2))

        # Check that the retina is removed if the retina would be too large.
        size1.width  = cd1.width - 20
        size1.height = cd1.height - 20
        size1.save()

        img1.render()

        # Check we don't prematurely delete the retina
        self.assert_(os.path.isfile(img1.retina_path))

        img1.save()

        self.assert_(not os.path.isfile(img1.retina_path))

    def test_size_aspect_ratio(self):
        """
        Tests that a bug in setting of aspect ratio is fixed.
        """
        size = CM.Size(slug='test', width=100, aspect_ratio=12)
        size.save()

        self.assertEquals(size.aspect_ratio, 12)

    def test_bad_mimetype(self):
        """
        Tests that we can handle incorrectly extensioned images.
        """
        NEW_TEST_IMAGE = TEST_IMAGE + '.gif.1'
        shutil.copyfile(TEST_IMAGE, NEW_TEST_IMAGE)

        cd1 = self.get_test_image(NEW_TEST_IMAGE)

        img = cd1.new_derived_image()
        size = CM.Size(slug='thumbnail',
                            width=128,
                            height=128,
                            retina=True)
        size.save()

        img.size = size
        # Since the the extension is clearly incorrect (should be jpeg), it should still
        # save it as jpeg
        img.render()
        img.save()

    def test_attribution_cascade(self):
        """
        Tests that attribution is correctly propagated through from originals
        to children.
        """
        cd1 = self.get_test_image()
        
        img = cd1.new_derived_image()

        img.set_manual_size(width=100, height=100).save()
        img.render()

        img.save()

        self.assertEquals(img.metadata.attribution,
                          cd1.metadata.attribution)
        self.assertEquals(img.metadata.caption,
                          cd1.metadata.caption)

    def test_recursive_save(self):
        """
        Tests that we recursively save all root and intermediate images 
        when saving a leaf image, if they have not been saved.
        """
        cd1 = CM.Image(image=TEST_IMAGE)
        d1 = cd1.new_derived_image()
        d2 = d1.new_derived_image()
        d3 = d2.new_derived_image()
        d4 = d3.new_derived_image()

        # Nothing's been saved, so nothing should have an id.
        images = (cd1, d1, d2, d3)
        for i in images:
            self.assertEquals(i.pk, None)

        # Save partway
        d2.save()

        # Check that the ancestors were saved.
        last = None
        for i in (cd1, d1, d2):
            self.assert_(i.pk > last)
            last = i.pk

        # Check that the descendents are NOT saved
        for i in (d3,d4):
            self.assertEquals(i.pk, None)

        d4.save()
        last = None
        for i in images:
            self.assert_(i.pk > last) 
            last = i.pk

    def test_variable_dimension(self):
        """
        Tests that variable dimensions work properly.
        """
        cd1 = self.get_test_image()

        img = cd1.new_derived_image()
        size = CM.Size(slug='thumbnail',
                            width=128,
                            retina=True)

        size.save()
        img.size = size

        img.set_crop(100,100,400,400).save()

        img.render()
        img.save()

        self.assertEquals(img.width, 128)
        self.assertEquals(img.height, 128)

        img.set_crop(1,1,128,256).save()

        img.render()
        img.save()

        self.assertEquals(img.width, 128)
        self.assertEquals(img.height, 256)

    def test_from_stream(self):
        """
        Tests that streaming in data saves correctly, and into the correct location.
        """
        # Fake loading it from a stream.
        cd1 = self.get_test_image(image=None)
        cf = ContentFile(file(TEST_IMAGE).read())
        basename = os.path.basename(TEST_IMAGE)
        cd1.image.save(basename, cf)
        cd1.save()

        self.assert_(settings.UPLOAD_PATH in cd1.image.path)
        self.assertEquals(cd1.image.width, 897)

    def test_custom_upload_to(self):
        """
        Tests whether we can set a custom cropduster upload to path.
        """
        tm = TestModel()
        # Get the proxy image class
        image_cls = tm._meta.get_field_by_name('image')[0].rel.to 
        image = image_cls()

        # Mimic uploading img
        cf = ContentFile(file(TEST_IMAGE).read())
        basename = os.path.basename(TEST_IMAGE)
        image.image.save(basename, cf)
        image.save()
        tm.image = image
        tm.save()

        path = datetime.datetime.now().strftime('/test/%Y/%m/%d')
        self.assert_(path in tm.image.image.name)

    def test_dynamic_path(self):
        self.create_size_sets()
        tm = TestModel2()

        # Get the proxy image class
        image_cls = tm._meta.get_field_by_name('image')[0].rel.to 
        image = image_cls()

        # Mimic uploading img
        cf = ContentFile(file(TEST_IMAGE).read())
        basename = os.path.basename(TEST_IMAGE)
        image.image.save(basename, cf)
        image.save()

        # Setup the children
        for derived in image.add_size_set(name='Facebook'):
            derived.render()
            derived.save()

        # Base assert
        self.assert_( image.image.name.endswith( '/1/%s' % basename ),
                      "Path mismatch: %s, %s" % (image.image.name, basename) )
        old_name = image.image.name

        # Save the model
        tm.image = image
        tm.save()

        self.assert_( image.image.name.endswith( '/2/%s' % basename ),
                      "Path mismatch: %s, %s" % (image.image.name, basename) )

        self.assert_(os.path.isfile(tm.image.image.path), "Path %s is missing" % tm.image.image.path)

        tm.slug = 'foobar'
        tm.save()

        self.assert_( image.image.name.endswith( '/3/foobar/%s' % basename ),
                      "Path mismatch: %s, %s" % (image.image.name, basename) )

        # Everything should be different now...
        self.assert_(os.path.isfile(tm.image.image.path), "Path %s is missing" % tm.image.image.path)

        # Check that the children's retina images have moved
        for image in tm.image.descendants:
            if image.size.retina:
                self.assert_(os.path.isfile(image.retina_path), "Retina didn't get moved!")

    def test_proxy_image_convert(self):
        """
        Tests that regular cropduster image saved to fields which use proxy versions.   
        """
        cd1 = self.get_test_image()
        t = TestModel()
        t.image = cd1
        self.assert_(isinstance(cd1, CM.Image))
        self.assertNotEquals(type(cd1), CM.Image)
        self.assert_(issubclass(type(cd1), CM.Image))

        try:
            t.image = object()
            self.fail("This shouldn't be allowed!")
        except ValueError:
            pass

    def test_absolute_url(self):
        """
        Tests whether absolute urls are created correctly.
        """
        cd1 = self.get_test_image()
        cd1.save()

        image_basename = os.path.basename(TEST_IMAGE)

        # Test without hash
        image_url = cd1.get_absolute_url(False)
        self.assertEquals(image_url, os.path.join(settings.STATIC_URL, cd1.image.url))

        # Test with hash
        image_url_hash = cd1.get_absolute_url()
        self.assert_('?' in image_url_hash, "Missing timestamp hash")

        last_timestamp = None
        for i in xrange(2):
            # Re-save to update the date_modified timestamp
            cd1.save()
            # Check the timestamp changed
            self.assertNotEquals(last_timestamp, cd1.date_modified)
            last_timestamp = cd1.date_modified

            raw_url, timestamp = image_url_hash.split('?')
            self.assertEquals(raw_url, image_url)

            # Convert the hex back to the original
            hashed_time = datetime.datetime.fromtimestamp(int(timestamp, 16))

            # No microseconds on hashes, giving us a hash granularity 
            # of one second.
            date_modified = cd1.date_modified - \
                datetime.timedelta(microseconds = cd1.date_modified.microsecond)

            self.assertEquals(date_modified, hashed_time)
            
class TestModel(models.Model):
    image = CM.CropDusterField(upload_to='test/%Y/%m/%d')
    image2 = CM.CropDusterField(null=True, related_name='image2')
    image3 = CM.CropDusterField(to=CM.Image, null=True, related_name='image3')

class Counter(object):
    counter = 0
    def  __call__(self, filename, instance=None):
        self.counter += 1
        counter = `self.counter`
        if instance is None:
            return '%s/%s' % (counter, filename)

        return os.path.join(counter, instance.slug, filename)

class TestModel2(models.Model):
    slug = ""
    image = CM.CropDusterField(upload_to=Counter(),
                               dynamic_path=True)

if __name__ == '__main__':
    unittest.main()
