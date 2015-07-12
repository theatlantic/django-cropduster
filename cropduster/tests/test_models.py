from __future__ import absolute_import, division

import os
import PIL
import uuid
import shutil

from django import test
from django.contrib.contenttypes.models import ContentType

from .helpers import CropdusterTestCaseMediaMixin
from .models import Article, Author, TestForOptionalSizes, TestMultipleFieldsInheritanceChild
from ..models import Size, Image
from ..exceptions import CropDusterResizeException


class TestImage(CropdusterTestCaseMediaMixin, test.TestCase):

    def setUp(self):
        super(TestImage, self).setUp()
        author = Author.objects.create(name="Samuel Langhorne Clemens")
        article = Article.objects.create(title="Pudd'nhead Wilson",
            author=author, lead_image=os.path.join(self.TEST_IMG_DIR_RELATIVE, 'img.jpg'))
        article.lead_image.generate_thumbs()

        self.article_ct = ContentType.objects.get(app_label='cropduster', model='article')
        self.article = Article.objects.get(pk=article.pk)
        self.author = author

    def test_original_image(self):
        article = self.article
        self.assertEqual(article.lead_image.width, 674)
        self.assertEqual(article.lead_image.height, 800)
        self.assertIs(article.lead_image.sizes, Article.LEAD_IMAGE_SIZES)

    def test_generate_thumbs(self):
        article = self.article
        sizes = sorted(list(Size.flatten(Article.LEAD_IMAGE_SIZES)), key=lambda x: x.name)
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
        article = Article.objects.create(title="Img Too Small", author=self.author, lead_image=new_filepath)
        self.assertRaises(CropDusterResizeException, article.lead_image.generate_thumbs)

    def test_prefetch_related_with_images(self):
        for x in range(3):
            imgpath = os.path.join(self.TEST_IMG_DIR, '%s.jpg' % uuid.uuid4().hex)
            shutil.copyfile(os.path.join(self.TEST_IMG_DIR, 'img.jpg'), imgpath)
            article = Article.objects.create(title="", author=self.author, lead_image=imgpath)
            article.lead_image.generate_thumbs()

        with self.assertNumQueries(2):
            articles = Article.objects.filter(pk__in=[article.pk])
            for article in articles.prefetch_related('lead_image'):
                article.lead_image.related_object

        with self.assertNumQueries(3):
            articles = Article.objects.filter(pk__in=[article.pk])
            for article in articles.prefetch_related('lead_image__thumbs'):
                list(article.lead_image.related_object.thumbs.all())

    def test_redundant_prefetch_related_args_with_images(self):
        for x in range(3):
            imgpath = os.path.join(self.TEST_IMG_DIR, '%s.jpg' % uuid.uuid4().hex)
            shutil.copyfile(os.path.join(self.TEST_IMG_DIR, 'img.jpg'), imgpath)
            article = Article.objects.create(title="", author=self.author, lead_image=imgpath)
            article.lead_image.generate_thumbs()

        with self.assertNumQueries(3):
            articles = Article.objects.filter(pk__in=[article.pk])
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
            article = Article.objects.create(title="", author=self.author,
                lead_image=img_path, alt_image=img_path_alt)
            article.lead_image.generate_thumbs()
            article.alt_image.generate_thumbs()
            img_map[article.pk] = (img_name, img_name_alt)

        with self.assertNumQueries(5):
            articles = Article.objects.filter(id__in=img_map.keys()).prefetch_related(
               'lead_image__thumbs', 'alt_image__thumbs')
            for article in articles:
                lead_name, alt_name = img_map[article.pk]
                self.assertTrue(lead_name in article.lead_image.related_object.path)
                self.assertTrue(alt_name in article.alt_image.related_object.path)

                lead_sizes = [s.name for s in Size.flatten(Article.LEAD_IMAGE_SIZES)]
                lead_thumbs = list(article.lead_image.related_object.thumbs.all())
                self.assertEqual(len(lead_thumbs), len(lead_sizes))
                for thumb in lead_thumbs:
                    self.assertEqual(thumb.image_id, article.lead_image.related_object.pk)
                    self.assertTrue(thumb.name in lead_sizes)

                alt_sizes = [s.name for s in Size.flatten(Article.ALT_IMAGE_SIZES)]
                alt_thumbs = list(article.alt_image.related_object.thumbs.all())
                self.assertEqual(len(alt_thumbs), len(alt_sizes))
                for thumb in alt_thumbs:
                    self.assertEqual(thumb.image_id, article.alt_image.related_object.pk)
                    self.assertTrue(thumb.name in alt_sizes)

    def test_prefetch_related_through_table(self):
        author = Author.objects.create(name="Author")
        for x in range(10):
            imgpath = os.path.join(self.TEST_IMG_DIR, '%s.jpg' % uuid.uuid4().hex)
            shutil.copyfile(os.path.join(self.TEST_IMG_DIR, 'img.jpg'), imgpath)
            alt_imgpath = os.path.join(self.TEST_IMG_DIR, '%s.png' % uuid.uuid4().hex)
            shutil.copyfile(os.path.join(self.TEST_IMG_DIR, 'img.png'), alt_imgpath)
            article = Article.objects.create(title="prefetch", author=author, lead_image=imgpath, alt_image=alt_imgpath)
            article.lead_image.generate_thumbs()
            article.alt_image.generate_thumbs()

        lead_sizes = [s.name for s in Size.flatten(Article.LEAD_IMAGE_SIZES)]
        alt_sizes = [s.name for s in Size.flatten(Article.ALT_IMAGE_SIZES)]

        with self.assertNumQueries(6):
            authors = Author.objects.filter(pk=author.pk).prefetch_related(
                'article_set__lead_image__thumbs',
                'article_set__alt_image__thumbs')
            for author in authors:
                for article in author.article_set.all():
                    self.assertTrue(article.lead_image.path.endswith('jpg'))
                    self.assertTrue(article.alt_image.path.endswith('png'))
                    for thumb in article.lead_image.related_object.thumbs.all():
                        self.assertTrue(thumb.name in lead_sizes)
                    for thumb in article.alt_image.related_object.thumbs.all():
                        self.assertTrue(thumb.name in alt_sizes)


class TestModelSaving(CropdusterTestCaseMediaMixin, test.TestCase):

    def test_save_image_updates_model(self):
        img_path = os.path.join(self.TEST_IMG_DIR, 'img.png')
        article = Article.objects.create(title="test", author=Author.objects.create(name='test'))
        Image.objects.create(content_type=ContentType.objects.get(app_label='cropduster', model='article'),
                             object_id=article.pk,
                             image=img_path)
        self.assertFalse(article.lead_image)

        # Refresh the article from the database
        article = Article.objects.get(pk=article.pk)
        self.assertTrue(article.lead_image)
        self.assertEqual(article.lead_image.path, img_path)

    def test_resave_single_image_model(self):
        author = Author(name='test')
        author.headshot = os.path.join(self.TEST_IMG_DIR_RELATIVE, 'img.jpg')
        author.save()

        author = Author.objects.get(pk=author.pk)
        author.save()

        author = Author.objects.get(pk=author.pk)
        self.assertTrue(author.headshot.path.endswith('img.jpg'))

    def test_resave_single_image_model_with_thumbs(self):
        author = Author(name='test')
        author.headshot = os.path.join(self.TEST_IMG_DIR_RELATIVE, 'img.jpg')
        author.save()

        author.headshot.generate_thumbs()

        author = Author.objects.get(pk=author.pk)
        author.save()

        author = Author.objects.get(pk=author.pk)
        self.assertTrue(author.headshot.path.endswith('img.jpg'))

    def test_resave_multi_image_model_with_one_image(self):
        article = Article(title="title", author=Author.objects.create(name='test'))
        article.lead_image = os.path.join(self.TEST_IMG_DIR_RELATIVE, 'img.jpg')
        article.save()

        article = Article.objects.get(pk=article.pk)
        article.save()

        article = Article.objects.get(pk=article.pk)
        self.assertTrue(article.lead_image.path.endswith('img.jpg'))

    def test_resave_multi_image_model_with_one_image_and_thumbs(self):
        article = Article(title="title", author=Author.objects.create(name='test'))
        article.lead_image = os.path.join(self.TEST_IMG_DIR_RELATIVE, 'img.jpg')
        article.save()

        article.lead_image.generate_thumbs()

        article = Article.objects.get(pk=article.pk)
        article.save()

        article = Article.objects.get(pk=article.pk)
        self.assertTrue(article.lead_image.path.endswith('img.jpg'))

    def test_resave_multi_image_model_with_two_images(self):
        article = Article(title="title", author=Author.objects.create(name='test'))
        article.lead_image = os.path.join(self.TEST_IMG_DIR_RELATIVE, 'img.jpg')
        article.alt_image = os.path.join(self.TEST_IMG_DIR_RELATIVE, 'img.png')
        article.save()

        article = Article.objects.get(pk=article.pk)
        article.save()

        article = Article.objects.get(pk=article.pk)
        self.assertTrue(article.lead_image.path.endswith('img.jpg'))
        self.assertTrue(article.alt_image.path.endswith('img.png'))

    def test_resave_multi_image_model_with_two_images_and_thumbs(self):
        article = Article(title="title", author=Author.objects.create(name='test'))
        article.lead_image = os.path.join(self.TEST_IMG_DIR_RELATIVE, 'img.jpg')
        article.alt_image = os.path.join(self.TEST_IMG_DIR_RELATIVE, 'img.png')
        article.save()

        article.lead_image.generate_thumbs()
        article.alt_image.generate_thumbs()

        article = Article.objects.get(pk=article.pk)
        article.save()

        article = Article.objects.get(pk=article.pk)
        self.assertTrue(article.lead_image.path.endswith('img.jpg'))
        self.assertTrue(article.alt_image.path.endswith('img.png'))

    def test_change_image_on_model_with_two_images(self):
        article = Article(title="title", author=Author.objects.create(name='test'))
        article.lead_image = os.path.join(self.TEST_IMG_DIR_RELATIVE, 'img.jpg')
        article.save()

        article = Article.objects.get(pk=article.pk)
        article.alt_image = os.path.join(self.TEST_IMG_DIR_RELATIVE, 'img.png')
        article.save()

        article = Article.objects.get(pk=article.pk)
        self.assertTrue(article.lead_image.path.endswith('img.jpg'))
        self.assertTrue(article.alt_image.path.endswith('img.png'))

    def test_optional_sizes(self):
        test_a = TestForOptionalSizes.objects.create(slug='a')
        test_a.image = os.path.join(self.TEST_IMG_DIR_RELATIVE, 'img.jpg')
        test_a.save()
        test_a.image.generate_thumbs()

        image = Image.objects.get(content_type=ContentType.objects.get_for_model(test_a),
            object_id=test_a.pk)
        num_thumbs = len(image.thumbs.all())
        self.assertEqual(num_thumbs, 1, "Expected one thumb; instead got %d" % num_thumbs)

        test_b = TestForOptionalSizes.objects.create(slug='b')
        test_b.image = os.path.join(self.TEST_IMG_DIR_RELATIVE, 'img2.jpg')
        test_b.save()
        test_b.image.generate_thumbs()

        image = Image.objects.get(content_type=ContentType.objects.get_for_model(test_b),
            object_id=test_b.pk)
        num_thumbs = len(image.thumbs.all())
        self.assertEqual(num_thumbs, 2, "Expected one thumb; instead got %d" % num_thumbs)

    def test_multiple_fields_with_inheritance(self):
        child_fields = [f.name for f in TestMultipleFieldsInheritanceChild._meta.local_fields]
        self.assertNotIn('image', child_fields,
            "Field 'image' from parent model should not be in the child model's local_fields")
