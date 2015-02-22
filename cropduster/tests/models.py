from django.db import models
from django.contrib import admin

from cropduster.models import CropDusterField, Size


class Author(models.Model):
    name = models.CharField(max_length=255)
    HEADSHOT_SIZES = [
        Size('main', w=220, h=180, auto=[
            Size('thumb', w=110, h=90),
        ]),
    ]
    headshot = CropDusterField(upload_to="author/headshots/%Y/%m", sizes=HEADSHOT_SIZES)

    class Meta:
        app_label = 'cropduster'


class Article(models.Model):
    title = models.CharField(max_length=255)
    author = models.ForeignKey(to=Author)
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
