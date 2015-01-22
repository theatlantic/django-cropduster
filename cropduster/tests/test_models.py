from __future__ import absolute_import, division

import os
import PIL

from django.contrib.contenttypes.models import ContentType

from . import CropdusterTestCase
from .models import TestArticle, TestAuthor
from ..models import Size, Image
from ..exceptions import CropDusterResizeException


class TestImage(CropdusterTestCase):

    def setUp(self):
        super(TestImage, self).setUp()
        author = TestAuthor.objects.create(name="Samuel Langhorne Clemens")
        article = TestArticle.objects.create(title="Pudd'nhead Wilson",
            author=author, lead_image=os.path.join(self.TEST_IMG_DIR, 'img.jpg'))
        article.lead_image.generate_thumbs()

        self.article_ct = ContentType.objects.get(app_label='cropduster', model='testarticle')
        self.article = TestArticle.objects.get(pk=article.pk)
        self.author = author

    def test_original_image(self):
        article = self.article
        self.assertEqual(article.lead_image.width, 674)
        self.assertEqual(article.lead_image.height, 800)
        self.assertIs(article.lead_image.sizes, TestArticle.LEAD_IMAGE_SIZES)

    def test_generate_thumbs(self):
        article = self.article
        sizes = sorted(list(Size.flatten(TestArticle.LEAD_IMAGE_SIZES)), key=lambda x: x.name)
        thumbs = sorted(list(article.lead_image.related_object.thumbs.all()), key=lambda x: x.name)
        self.assertEqual(len(thumbs), len(sizes))
        for size, thumb in zip(sizes, thumbs):
            self.assertEqual(size.name, thumb.name)
            if size.width:
                self.assertEqual(size.width, thumb.width)
            if size.height:
                self.assertEqual(size.height, thumb.height)
            else:
                ratio = article.lead_image.height / article.lead_image.width
                self.assertAlmostEqual(thumb.height, ratio * size.width, delta=1)
            self.assertEqual(thumb.image.image, article.lead_image.related_object.image)
            self.assertTrue(os.path.exists(thumb.path))
            self.assertEqual((thumb.width, thumb.height), PIL.Image.open(thumb.path).size)

        old_filepath = os.path.join(self.TEST_IMG_DIR, 'img.jpg')
        path, filename = os.path.split(old_filepath)
        new_filepath = os.path.join(path, 'new-%s' % filename)
        image = PIL.Image.open(old_filepath)
        image.thumbnail((50, 50))
        image.save(new_filepath)
        article = TestArticle.objects.create(title="Img Too Small", author=self.author, lead_image=new_filepath)
        self.assertRaises(CropDusterResizeException, article.lead_image.generate_thumbs)

    def test_multiple_images(self):
        self.article.alt_image = os.path.join(self.TEST_IMG_DIR, 'img.png')
        self.article.save()
        self.article.alt_image.generate_thumbs()

        article = TestArticle.objects.get(pk=self.article.pk)

        lead_sizes = list(Size.flatten(TestArticle.LEAD_IMAGE_SIZES))
        lead_thumbs = list(article.lead_image.related_object.thumbs.all())
        self.assertEqual(len(lead_thumbs), len(lead_sizes))

        alt_sizes = list(Size.flatten(TestArticle.ALT_IMAGE_SIZES))
        alt_thumbs = list(article.alt_image.related_object.thumbs.all())
        self.assertEqual(len(alt_thumbs), len(alt_sizes))

    def test_save(self):
        img_path = os.path.join(self.TEST_IMG_DIR, 'img.png')
        article = TestArticle.objects.create(title="Tom Sawyer Abroad", author=self.author)
        Image.objects.create(content_type=self.article_ct,
                             object_id=article.pk,
                             image=img_path)
        self.assertFalse(article.lead_image)

        # Refresh the article from the database
        article = TestArticle.objects.get(pk=article.pk)
        self.assertTrue(article.lead_image)
        self.assertEqual(article.lead_image.path, img_path)
