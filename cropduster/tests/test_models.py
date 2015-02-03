from __future__ import absolute_import, division

import os
import PIL
import uuid
import shutil

from django import test
from django.contrib.contenttypes.models import ContentType

from .helpers import CropdusterTestCaseMediaMixin
from .models import TestArticle, TestAuthor
from ..models import Size, Image
from ..exceptions import CropDusterResizeException


class TestImage(CropdusterTestCaseMediaMixin, test.TestCase):

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

    def test_prefetch_related_with_images(self):
        for x in range(3):
            imgpath = os.path.join(self.TEST_IMG_DIR, '%s.jpg' % uuid.uuid4().hex)
            shutil.copyfile(os.path.join(self.TEST_IMG_DIR, 'img.jpg'), imgpath)
            article = TestArticle.objects.create(title="", author=self.author, lead_image=imgpath)
            article.lead_image.generate_thumbs()

        with self.assertNumQueries(2):
            articles = TestArticle.objects.filter(pk__in=[article.pk])
            for article in articles.prefetch_related('lead_image'):
                article.lead_image.related_object

        with self.assertNumQueries(3):
            articles = TestArticle.objects.filter(pk__in=[article.pk])
            for article in articles.prefetch_related('lead_image__thumbs'):
                list(article.lead_image.related_object.thumbs.all())

    def test_redundant_prefetch_related_args_with_images(self):
        for x in range(3):
            imgpath = os.path.join(self.TEST_IMG_DIR, '%s.jpg' % uuid.uuid4().hex)
            shutil.copyfile(os.path.join(self.TEST_IMG_DIR, 'img.jpg'), imgpath)
            article = TestArticle.objects.create(title="", author=self.author, lead_image=imgpath)
            article.lead_image.generate_thumbs()

        with self.assertNumQueries(3):
            articles = TestArticle.objects.filter(pk__in=[article.pk])
            for article in articles.prefetch_related('lead_image', 'lead_image__thumbs'):
                list(article.lead_image.related_object.thumbs.all())

    def test_prefetch_related_with_alt_images(self):
        img_map = {}
        for x in range(3):
            img_name = uuid.uuid4().hex
            img_name_alt = uuid.uuid4().hex
            img_path = os.path.join(self.TEST_IMG_DIR, img_name, 'original.jpg')
            img_path_alt = os.path.join(self.TEST_IMG_DIR, img_name_alt, 'original.jpg')
            os.mkdir(os.path.dirname(img_path))
            os.mkdir(os.path.dirname(img_path_alt))
            shutil.copyfile(os.path.join(self.TEST_IMG_DIR, 'img.jpg'), img_path)
            shutil.copyfile(os.path.join(self.TEST_IMG_DIR, 'img.jpg'), img_path_alt)
            article = TestArticle.objects.create(title="", author=self.author,
                lead_image=img_path, alt_image=img_path_alt)
            article.lead_image.generate_thumbs()
            article.alt_image.generate_thumbs()
            img_map[article.pk] = (img_name, img_name_alt)

        with self.assertNumQueries(5):
            articles = TestArticle.objects.filter(id__in=img_map.keys()).prefetch_related(
               'lead_image__thumbs', 'alt_image__thumbs')
            for article in articles:
                lead_name, alt_name = img_map[article.pk]
                self.assertTrue(lead_name in article.lead_image.related_object.path)
                self.assertTrue(alt_name in article.alt_image.related_object.path)

                lead_sizes = [s.name for s in Size.flatten(TestArticle.LEAD_IMAGE_SIZES)]
                lead_thumbs = list(article.lead_image.related_object.thumbs.all())
                self.assertEqual(len(lead_thumbs), len(lead_sizes))
                for thumb in lead_thumbs:
                    self.assertEqual(thumb.image_id, article.lead_image.related_object.pk)
                    self.assertTrue(thumb.name in lead_sizes)

                alt_sizes = [s.name for s in Size.flatten(TestArticle.ALT_IMAGE_SIZES)]
                alt_thumbs = list(article.alt_image.related_object.thumbs.all())
                self.assertEqual(len(alt_thumbs), len(alt_sizes))
                for thumb in alt_thumbs:
                    self.assertEqual(thumb.image_id, article.alt_image.related_object.pk)
                    self.assertTrue(thumb.name in alt_sizes)

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
