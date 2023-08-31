from django.db import models

from cropduster.fields import ReverseForeignRelation
from cropduster.models import CropDusterField, Size


class Author(models.Model):
    name = models.CharField(max_length=255)
    HEADSHOT_SIZES = [
        Size('main', w=220, h=180, auto=[
            Size('thumb', w=110, h=90),
        ]),
    ]
    headshot = CropDusterField(upload_to="author/headshots/%Y/%m", sizes=HEADSHOT_SIZES,
        related_name="author_headshotset")


class Article(models.Model):
    title = models.CharField(max_length=255)
    author = models.ForeignKey(to=Author, blank=True, null=True,
        on_delete=models.SET_NULL)
    LEAD_IMAGE_SIZES = [
        Size('main', w=600, h=480, auto=[
            Size('thumb', w=110, h=90),
        ]),
        Size('no_height', w=600),
    ]
    ALT_IMAGE_SIZES = [
        Size('wide', w=600, h=300),
    ]
    lead_image = CropDusterField(upload_to="article/lead_image/%Y/%m",
                                db_column='image',
                                related_name="test_article_lead_image",
                                sizes=LEAD_IMAGE_SIZES)
    alt_image = CropDusterField(upload_to="article/alt_image/%Y/%m",
                                related_name="test_article_alt_image",
                                sizes=ALT_IMAGE_SIZES,
                                field_identifier="alt")


class OptionalSizes(models.Model):

    TEST_SIZES = [
        Size('main', w=600, h=480, auto=[
            Size('optional', w=1200, h=960, required=False),
        ])]

    slug = models.SlugField()
    image = CropDusterField(upload_to="test", sizes=TEST_SIZES)


class OrphanedThumbs(models.Model):

    TEST_SIZES = [
        Size('main', w=600, h=480, auto=[
            Size('main@2x', w=1200, h=960),
        ]),
        Size('secondary', w=600, h=480, auto=[
            Size('secondary@2x', w=1200, h=960),
        ])]

    slug = models.SlugField()
    image = CropDusterField(upload_to="test", sizes=TEST_SIZES)


class MultipleFieldsInheritanceParent(models.Model):

    slug = models.SlugField()
    image = CropDusterField(upload_to="test", sizes=[Size('main', w=600, h=480)])


class MultipleFieldsInheritanceChild(MultipleFieldsInheritanceParent):

    image2 = CropDusterField(upload_to="test", sizes=[Size('main', w=600, h=480)],
        field_identifier="2")


class ReverseForeignRelA(models.Model):
    slug = models.SlugField()
    c = models.ForeignKey('ReverseForeignRelC', on_delete=models.CASCADE)
    a_type = models.CharField(max_length=10, choices=(
        ("x", "X"),
        ("y", "Y"),
        ("z", "Z"),
    ))

    def __str__(self):
        return self.slug


class ReverseForeignRelB(models.Model):
    slug = models.SlugField()
    c = models.ForeignKey('ReverseForeignRelC', on_delete=models.CASCADE)

    def __str__(self):
        return self.slug


class ReverseForeignRelC(models.Model):
    slug = models.SlugField()
    rel_a = ReverseForeignRelation(
        ReverseForeignRelA, field_name='c', limit_choices_to={'a_type': 'x'})
    rel_b = ReverseForeignRelation(ReverseForeignRelB, field_name='c')

    def __str__(self):
        return self.slug


class ReverseForeignRelM2M(models.Model):
    slug = models.SlugField()
    m2m = models.ManyToManyField(ReverseForeignRelC)

    def __str__(self):
        return self.slug
