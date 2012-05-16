import unittest
import os

from django.conf import settings
PATH = os.path.split(__file__)[0]
settings.MEDIA_ROOT = settings.STATIC_ROOT = settings.UPLOAD_PATH = PATH

from django.core.exceptions import ObjectDoesNotExist as DNE, ValidationError
import cropduster.models as CM

abspath = lambda x: os.path.join(PATH, x)

def save_all(objs):
    for o in objs:
        o.save()

def delete_all(model):
    i = -1
    for i, o in enumerate(model.objects.all()):
        o.delete()

class TestCropduster(unittest.TestCase):
    def setUp(self):
        pass

    def tearDown(self):
        # Delete all objects
        delete_all( CM.Image )
        delete_all( CM.ImageSizeSet )
        delete_all( CM.ImageSize )
        delete_all( CM.Crop )
    
    def create_size_sets(self):
        iss = CM.ImageSizeSet(name='Facebook', slug='facebook')
        iss.save()

        thumb = CM.ImageSize(name='Thumbnail',
                             slug='thumb',
                             width=60,
                             height=60,
                             auto_crop=True,
                             retina=True,
                             size_set=iss)
        thumb.save()

        banner = CM.ImageSize(name='Banner',
                              slug='banner',
                              width=1024,
                              aspect_ratio=1.3,
                              size_set=iss)
                                
        banner.save()

        iss2 = CM.ImageSizeSet(name='Mobile', slug='mobile')
        iss2.save()

        splash = CM.ImageSize(name='Headline',
                              slug='headline',
                              width=500,
                              height=400,
                              retina=True,
                              auto_crop=True,
                              size_set=iss2)

        splash.save()

    def get_test_image(self):
        cd1 = CM.Image()
        cd1.image = abspath('testdata/img1.jpg')
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
        
        # Should it return 0 or 2?
        self.assertEquals(len(images), 0)

        self.assertEquals(cd1.size_sets.count(), 1)

        # Try adding one that doesn't exist
        self.failUnlessRaises(DNE, cd1.add_size_set, name='foobar')

        # Add another new size_set
        new_images = cd1.add_size_set(slug='mobile')
        self.assertEquals(len(new_images), 1)

        save_all(new_images)

        self.assertEquals(cd1.derived.count(), 3)

    def test_render_derived(self):
        """
        Tests that we can correctly render derived images from the original.
        """
        self.create_size_sets()

        cd1 = self.get_test_image()
        image = cd1.add_size_set(slug='mobile')[0]

        # Should throw an error if the image isn't saved
        self.assertEquals(image.can_render(), False)
        self.failUnlessRaises(ValidationError, image.render)

        image.save()

        self.assertEquals(image.can_render(), True)
        image.render()

        size = image.size
        self.assertEquals(image.width, size.width)
        self.assertEquals(image.height, size.height)

if __name__ == '__main__':
    unittest.main()
