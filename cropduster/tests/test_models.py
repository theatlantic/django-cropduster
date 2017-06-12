from __future__ import absolute_import, division

import os
import PIL

from django.test import TestCase
from django.contrib.contenttypes.models import ContentType
from django.utils.six.moves import range

from .helpers import CropdusterTestCaseMediaMixin
from .models import (
    Article, Author, TestForOptionalSizes, TestMultipleFieldsInheritanceChild,
    TestReverseForeignRelA, TestReverseForeignRelB, TestReverseForeignRelC,
    TestReverseForeignRelM2M, TestForOrphanedThumbs)
from cropduster.models import Size, Image, Thumb
from cropduster.exceptions import CropDusterResizeException


class TestImage(CropdusterTestCaseMediaMixin, TestCase):

    def setUp(self):
        super(TestImage, self).setUp()
        self.author = Author.objects.create(name="Samuel Langhorne Clemens")

    def test_original_image(self):
        article = Article.objects.create(title="Pudd'nhead Wilson",
            author=self.author, lead_image=self.create_unique_image('img.jpg'))
        article.lead_image.generate_thumbs()
        article = Article.objects.get(pk=article.pk)
        self.assertEqual(article.lead_image.width, 674)
        self.assertEqual(article.lead_image.height, 800)
        self.assertIs(article.lead_image.sizes, Article.LEAD_IMAGE_SIZES)

    def test_generate_thumbs(self):
        article = Article.objects.create(title="Pudd'nhead Wilson",
            author=self.author, lead_image=self.create_unique_image('img.jpg'))
        article.lead_image.generate_thumbs()
        article = Article.objects.get(pk=article.pk)
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

        image = PIL.Image.open(os.path.join(self.TEST_IMG_DIR, 'img.jpg'))
        image.thumbnail((50, 50))
        image.save(os.path.join(self.TEST_IMG_DIR, 'new-img.jpg'))
        new_image_path = self.create_unique_image('new-img.jpg')
        article = Article.objects.create(
            title="Img Too Small", author=self.author, lead_image=new_image_path)
        self.assertRaises(CropDusterResizeException, article.lead_image.generate_thumbs)

    def test_prefetch_related_with_images(self):
        for x in range(3):
            lead_image = self.create_unique_image('img.jpg')
            article = Article.objects.create(title="", author=self.author, lead_image=lead_image)
            article.lead_image.generate_thumbs()

        with self.assertNumQueries(2):
            articles = Article.objects.filter(pk__in=[article.pk])
            for article in articles.prefetch_related('lead_image'):
                article.lead_image.related_object

        with self.assertNumQueries(3):
            articles = Article.objects.filter(pk__in=[article.pk])
            for article in articles.prefetch_related('lead_image__thumbs'):
                list(article.lead_image.related_object.thumbs.all())

    def test_prefetch_related_reverse_relation_cache(self):
        for x in range(3):
            lead_image = self.create_unique_image('img.jpg')
            article = Article.objects.create(title="", author=self.author, lead_image=lead_image)
            article.lead_image.generate_thumbs()

        with self.assertNumQueries(3):
            articles = Article.objects.filter(pk__in=[article.pk])
            for article in articles.prefetch_related('lead_image__thumbs'):
                for thumb in article.lead_image.related_object.thumbs.all():
                    thumb.image

    def test_redundant_prefetch_related_args_with_images(self):
        for x in range(3):
            lead_image = self.create_unique_image('img.jpg')
            article = Article.objects.create(title="", author=self.author, lead_image=lead_image)
            article.lead_image.generate_thumbs()

        with self.assertNumQueries(3):
            articles = Article.objects.filter(pk__in=[article.pk])
            for article in articles.prefetch_related('lead_image', 'lead_image__thumbs'):
                list(article.lead_image.related_object.thumbs.all())

    def test_prefetch_related_with_alt_images(self):
        img_map = {}
        for x in range(3):
            lead_image_path = self.create_unique_image('img.jpg')
            alt_image_path = self.create_unique_image('img.jpg')
            article = Article.objects.create(title="", author=self.author,
                lead_image=lead_image_path, alt_image=alt_image_path)
            article.lead_image.generate_thumbs()
            article.alt_image.generate_thumbs()
            img_map[article.pk] = (lead_image_path, alt_image_path)

        with self.assertNumQueries(5):
            articles = (Article.objects.filter(id__in=img_map.keys())
                .prefetch_related('lead_image__thumbs', 'alt_image__thumbs'))
            for article in articles:
                lead_name, alt_name = img_map[article.pk]
                self.assertEqual(lead_name, article.lead_image.related_object.image.name)
                self.assertEqual(alt_name, article.alt_image.related_object.image.name)

                lead_sizes = [s.name for s in Size.flatten(Article.LEAD_IMAGE_SIZES)]
                lead_thumbs = list(article.lead_image.related_object.thumbs.all())
                self.assertEqual(len(lead_thumbs), len(lead_sizes))
                for thumb in lead_thumbs:
                    self.assertEqual(thumb.image_id, article.lead_image.related_object.pk)
                    self.assertIn(thumb.name, lead_sizes)

                alt_sizes = [s.name for s in Size.flatten(Article.ALT_IMAGE_SIZES)]
                alt_thumbs = list(article.alt_image.related_object.thumbs.all())
                self.assertEqual(len(alt_thumbs), len(alt_sizes))
                for thumb in alt_thumbs:
                    self.assertEqual(thumb.image_id, article.alt_image.related_object.pk)
                    self.assertIn(thumb.name, alt_sizes)

    def test_prefetch_related_through_table(self):
        author = Author.objects.create(name="Author")
        for x in range(10):
            article = Article.objects.create(
                title="prefetch", author=author,
                lead_image=self.create_unique_image('img.jpg'),
                alt_image=self.create_unique_image('img.png'))
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
                        self.assertIn(thumb.name, lead_sizes)
                    for thumb in article.alt_image.related_object.thumbs.all():
                        self.assertIn(thumb.name, alt_sizes)


class TestModelSaving(CropdusterTestCaseMediaMixin, TestCase):

    def test_save_image_updates_model(self):
        img_path = self.create_unique_image('img.png')
        article = Article.objects.create(title="test", author=Author.objects.create(name='test'))
        article_ct = ContentType.objects.get_for_model(Article)
        Image.objects.create(
            content_type=article_ct,
            object_id=article.pk,
            image=img_path)
        self.assertFalse(article.lead_image)

        # Refresh the article from the database
        article = Article.objects.get(pk=article.pk)
        self.assertTrue(article.lead_image)
        self.assertEqual(article.lead_image.name, img_path)

    def test_resave_single_image_model(self):
        img_path = self.create_unique_image('img.jpg')
        author = Author(name='test')
        author.headshot = img_path
        author.save()

        author = Author.objects.get(pk=author.pk)
        author.save()

        author = Author.objects.get(pk=author.pk)
        self.assertEqual(author.headshot.name, img_path)

    def test_resave_single_image_model_with_thumbs(self):
        img_path = self.create_unique_image('img.jpg')
        author = Author(name='test')
        author.headshot = img_path
        author.save()

        author.headshot.generate_thumbs()

        author = Author.objects.get(pk=author.pk)
        author.save()

        author = Author.objects.get(pk=author.pk)
        self.assertEqual(author.headshot.name, img_path)

    def test_resave_multi_image_model_with_one_image(self):
        img_path = self.create_unique_image('img.jpg')
        article = Article(title="title", author=Author.objects.create(name='test'))
        article.lead_image = img_path
        article.save()

        article = Article.objects.get(pk=article.pk)
        article.save()

        article = Article.objects.get(pk=article.pk)
        self.assertEqual(article.lead_image.name, img_path)

    def test_resave_multi_image_model_with_one_image_and_thumbs(self):
        img_path = self.create_unique_image('img.jpg')
        article = Article(title="title", author=Author.objects.create(name='test'))
        article.lead_image = img_path
        article.save()

        article.lead_image.generate_thumbs()

        article = Article.objects.get(pk=article.pk)
        article.save()

        article = Article.objects.get(pk=article.pk)
        self.assertEqual(article.lead_image.name, img_path)

    def test_resave_multi_image_model_with_two_images(self):
        lead_image = self.create_unique_image('img.jpg')
        alt_image = self.create_unique_image('img.png')
        article = Article(title="title", author=Author.objects.create(name='test'))
        article.lead_image = lead_image
        article.alt_image = alt_image
        article.save()

        article = Article.objects.get(pk=article.pk)
        article.save()

        article = Article.objects.get(pk=article.pk)
        self.assertEqual(article.lead_image.name, lead_image)
        self.assertEqual(article.alt_image.name, alt_image)

    def test_resave_multi_image_model_with_two_images_and_thumbs(self):
        lead_image = self.create_unique_image('img.jpg')
        alt_image = self.create_unique_image('img.png')

        article = Article(title="title", author=Author.objects.create(name='test'))
        article.lead_image = lead_image
        article.alt_image = alt_image
        article.save()

        article.lead_image.generate_thumbs()
        article.alt_image.generate_thumbs()

        article = Article.objects.get(pk=article.pk)
        article.save()

        article = Article.objects.get(pk=article.pk)
        self.assertEqual(article.lead_image.name, lead_image)
        self.assertEqual(article.alt_image.name, alt_image)

    def test_change_image_on_model_with_two_images(self):
        lead_image = self.create_unique_image('img.jpg')
        alt_image = self.create_unique_image('img.png')

        article = Article(title="title", author=Author.objects.create(name='test'))
        article.lead_image = lead_image
        article.save()

        article = Article.objects.get(pk=article.pk)
        article.alt_image = alt_image
        article.save()

        article = Article.objects.get(pk=article.pk)
        self.assertEqual(article.lead_image.name, lead_image)
        self.assertEqual(article.alt_image.name, alt_image)

    def test_optional_sizes(self):
        test_a = TestForOptionalSizes.objects.create(slug='a')
        test_a.image = self.create_unique_image('img.jpg')
        test_a.save()
        test_a.image.generate_thumbs()

        image = Image.objects.get(content_type=ContentType.objects.get_for_model(test_a),
            object_id=test_a.pk)
        num_thumbs = len(image.thumbs.all())
        self.assertEqual(num_thumbs, 1, "Expected one thumb; instead got %d" % num_thumbs)

        test_b = TestForOptionalSizes.objects.create(slug='b')
        test_b.image = self.create_unique_image('img2.jpg')
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

    def test_orphaned_thumbs_after_delete(self):
        test_a = TestForOrphanedThumbs.objects.create(
            slug='a', image=self.create_unique_image('img2.jpg'))
        test_a.image.generate_thumbs()
        test_a = TestForOrphanedThumbs.objects.get(slug='a')
        test_a.delete()

        num_thumbs = len(Thumb.objects.all())
        self.assertEqual(num_thumbs, 0, "%d orphaned thumbs left behind after deletion")


class TestReverseForeignRelation(TestCase):

    def test_standard_manager(self):
        c = TestReverseForeignRelC.objects.create(slug='c-1')
        for i in range(0, 3):
            TestReverseForeignRelB.objects.create(slug="b-%d" % i, c=c)

        c = TestReverseForeignRelC.objects.get(pk=c.pk)
        self.assertEqual(len(c.rel_b.all()), 3)

    def test_standard_prefetch_related(self):
        for i in range(0, 2):
            m2m = TestReverseForeignRelM2M.objects.create(slug='standard-m2m-%d' % i)
            for j in range(0, 2):
                c = TestReverseForeignRelC.objects.create(slug='c-%d-%d' % (i, j))
                m2m.m2m.add(c)
                for k in range(0, 3):
                    TestReverseForeignRelB.objects.create(slug="b-%d-%d-%d" % (i, j, k), c=c)
        objs = TestReverseForeignRelM2M.objects.prefetch_related('m2m__rel_b')
        with self.assertNumQueries(3):
            for obj in objs:
                for m2m_obj in obj.m2m.all():
                    self.assertEqual(len(m2m_obj.rel_b.all()), 3)

    def test_manager_with_limit_choices_to(self):
        """
        A ReverseForeignRelation with limit_choices_to applies the filter to the manager
        """
        c = TestReverseForeignRelC.objects.create(slug='c-1')
        for i in range(0, 3):
            TestReverseForeignRelA.objects.create(slug="a-%d" % i, c=c, a_type="x")
        TestReverseForeignRelA.objects.create(slug="a-4", c=c, a_type="y")

        c = TestReverseForeignRelC.objects.get(pk=c.pk)
        a_len = len(c.rel_a.all())
        self.assertNotEqual(a_len, 4, "limit_choices_to filter not applied")
        self.assertNotEqual(a_len, 0, "manager returned no objects, expected 3")
        self.assertEqual(a_len, 3)

    def test_prefetch_related_with_limit_choices_to(self):
        for i in range(0, 2):
            m2m = TestReverseForeignRelM2M.objects.create(slug='standard-m2m-%d' % i)
            for j in range(0, 2):
                c = TestReverseForeignRelC.objects.create(slug='c-%d-%d' % (i, j))
                m2m.m2m.add(c)
                for k in range(0, 3):
                    TestReverseForeignRelA.objects.create(
                        slug="a-%d-%d-%d" % (i, j, k), c=c, a_type='x')
                TestReverseForeignRelA.objects.create(
                    slug="a-%d-%d-%d" % (i, j, 4), c=c, a_type='y')
        objs = TestReverseForeignRelM2M.objects.prefetch_related('m2m__rel_a')
        with self.assertNumQueries(3):
            for obj in objs:
                for m2m_obj in obj.m2m.all():
                    self.assertEqual(len(m2m_obj.rel_a.all()), 3)
