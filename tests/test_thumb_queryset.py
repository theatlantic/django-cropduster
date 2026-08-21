from django.test import SimpleTestCase, TestCase

from cropduster.models import Image, Thumb, prime_reference_thumbs

from .helpers import CropdusterTestCaseMediaMixin
from .models import Article, Author


class TestPrimeReferenceThumbs(SimpleTestCase):

    def test_unsaved_thumbs_do_not_share_the_none_primary_key(self):
        first = Thumb(name='first')
        second = Thumb(name='second')

        prime_reference_thumbs([first, second])

        field = Thumb._meta.get_field('reference_thumb')
        self.assertFalse(field.is_cached(first))
        self.assertFalse(field.is_cached(second))


class TestWithReferenceThumbs(CropdusterTestCaseMediaMixin, TestCase):

    def setUp(self):
        super(TestWithReferenceThumbs, self).setUp()
        author = Author.objects.create(name="Samuel Langhorne Clemens")
        article = Article.objects.create(
            title="Pudd'nhead Wilson", author=author,
            lead_image=self.create_unique_image('img.jpg'))
        article.lead_image.generate_thumbs()
        article.refresh_from_db()
        self.image = article.lead_image.related_object

    def auto_thumb_count(self):
        return Thumb.objects.filter(image=self.image, reference_thumb__isnull=False).count()

    def test_reference_thumb_costs_a_query_without_it(self):
        self.assertGreater(self.auto_thumb_count(), 0)

        thumbs = list(Thumb.objects.filter(image=self.image))
        with self.assertNumQueries(self.auto_thumb_count()):
            for thumb in thumbs:
                thumb.reference_thumb

    def test_reference_thumb_is_free_with_it(self):
        thumbs = list(Thumb.objects.filter(image=self.image).with_reference_thumbs())
        with self.assertNumQueries(0):
            for thumb in thumbs:
                thumb.reference_thumb

    def test_survives_filtering_after_the_call(self):
        thumbs = list(
            Thumb.objects.with_reference_thumbs().filter(image=self.image).order_by('name'))
        with self.assertNumQueries(0):
            for thumb in thumbs:
                thumb.reference_thumb

    def test_deferring_the_reference_column_costs_nothing_up_front(self):
        """Priming does not read deferred ``reference_thumb_id`` columns.

        Reading a deferred value refreshes its row from the database. When the
        reference column is deferred, the queryset leaves the references
        uncached so that evaluating it does not add one query per thumb.
        """
        with self.assertNumQueries(1):
            thumbs = list(Thumb.objects.filter(image=self.image)
                          .only('name').with_reference_thumbs())

        self.assertGreater(len(thumbs), 0)
        for thumb in thumbs:
            thumb.reference_thumb

    def test_references_still_resolve_correctly(self):
        thumbs = {
            t.name: t for t in Thumb.objects.filter(image=self.image).with_reference_thumbs()}
        self.assertEqual(thumbs['thumb'].reference_thumb, thumbs['main'])
        self.assertIsNone(thumbs['main'].reference_thumb)


class TestImageWithThumbs(CropdusterTestCaseMediaMixin, TestCase):

    def setUp(self):
        super(TestImageWithThumbs, self).setUp()
        author = Author.objects.create(name="Samuel Langhorne Clemens")
        for i in range(3):
            article = Article.objects.create(
                title="", author=author, lead_image=self.create_unique_image('img.jpg'))
            article.lead_image.generate_thumbs()

    def test_thumbs_and_their_references_come_in_two_queries(self):
        with self.assertNumQueries(2):
            images = list(Image.objects.with_thumbs())
            for image in images:
                for thumb in image.thumbs.all():
                    thumb.reference_thumb

    def test_thumbs_are_still_scoped_to_their_image(self):
        for image in Image.objects.with_thumbs():
            for thumb in image.thumbs.all():
                self.assertEqual(thumb.image_id, image.pk)
