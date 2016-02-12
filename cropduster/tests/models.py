import sys

from django.db import models
from django.conf import settings
from django.contrib import admin

from cropduster.models import CropDusterField, Size


if 'test' in sys.argv or 'runtests.py' in sys.argv:
    class DisableMigrations(object):
        def __contains__(self, item): return True
        def __getitem__(self, item): return "notmigrations"

    settings.MIGRATION_MODULES = DisableMigrations()


class Author(models.Model):
    name = models.CharField(max_length=255)
    HEADSHOT_SIZES = [
        Size('main', w=220, h=180, auto=[
            Size('thumb', w=110, h=90),
        ]),
    ]
    headshot = CropDusterField(upload_to="author/headshots/%Y/%m", sizes=HEADSHOT_SIZES,
        related_name="author_headshotset")

    class Meta:
        app_label = 'cropduster'


class Article(models.Model):
    title = models.CharField(max_length=255)
    author = models.ForeignKey(to=Author, blank=True, null=True,
        on_delete=models.SET_NULL)
    LEAD_IMAGE_SIZES = [
        Size(u'main', w=600, h=480, auto=[
            Size(u'thumb', w=110, h=90),
        ]),
        Size(u'no_height', w=600),
    ]
    ALT_IMAGE_SIZES = [
        Size(u'wide', w=600, h=300),
    ]
    lead_image = CropDusterField(upload_to="article/lead_image/%Y/%m",
                                db_column='image',
                                related_name="test_article_lead_image",
                                sizes=LEAD_IMAGE_SIZES)
    alt_image = CropDusterField(upload_to="article/alt_image/%Y/%m",
                                related_name="test_article_alt_image",
                                sizes=ALT_IMAGE_SIZES,
                                field_identifier="alt")

    class Meta:
        app_label = 'cropduster'


class TestForOptionalSizes(models.Model):

    TEST_SIZES = [
        Size('main', w=600, h=480, auto=[
            Size('optional', w=1200, h=960, required=False),
        ])]

    slug = models.SlugField()
    image = CropDusterField(upload_to="test", sizes=TEST_SIZES)

    class Meta:
        app_label = 'cropduster'


class TestForOrphanedThumbs(models.Model):

    TEST_SIZES = [
        Size('main', w=600, h=480, auto=[
            Size('main@2x', w=1200, h=960),
        ]),
        Size('secondary', w=600, h=480, auto=[
            Size('secondary@2x', w=1200, h=960),
        ])]

    slug = models.SlugField()
    image = CropDusterField(upload_to="test", sizes=TEST_SIZES)

    class Meta:
        app_label = 'cropduster'


class TestMultipleFieldsInheritanceParent(models.Model):

    slug = models.SlugField()
    image = CropDusterField(upload_to="test", sizes=[Size(u'main', w=600, h=480)])

    class Meta:
        app_label = 'cropduster'


class TestMultipleFieldsInheritanceChild(TestMultipleFieldsInheritanceParent):

    image2 = CropDusterField(upload_to="test", sizes=[Size(u'main', w=600, h=480)],
        field_identifier="2")

    class Meta:
        app_label = 'cropduster'
