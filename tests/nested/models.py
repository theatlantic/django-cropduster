"""
Models for two levels of sortable nested inlines.

``NestedRoot -> NestedSection -> NestedItem`` matches the downstream
arrangement covered by these tests. Each item has two Cropduster fields,
distinguished by ``field_identifier``. The resulting formset names include
``section_set-0-items-0-image`` and its ``-0-`` Cropduster subformset, which
downstream POST handlers read directly.
"""

from django.db import models

from cropduster.models import CropDusterField, Size


class NestedRoot(models.Model):
    title = models.CharField(max_length=255)

    def __str__(self):
        return self.title


class NestedSection(models.Model):
    root = models.ForeignKey(
        NestedRoot, related_name='section_set', on_delete=models.CASCADE)
    name = models.CharField(max_length=255, blank=True)
    position = models.PositiveIntegerField(blank=True, null=True)

    class Meta:
        ordering = ('position',)

    def __str__(self):
        return self.name


class NestedItem(models.Model):

    IMAGE_SIZES = [
        Size('main', w=400, h=300, auto=[
            Size('thumb', w=100, h=75),
        ]),
    ]
    ALT_IMAGE_SIZES = [
        Size('wide', w=600, h=300),
    ]

    section = models.ForeignKey(
        NestedSection, related_name='items', on_delete=models.CASCADE)
    position = models.PositiveIntegerField(blank=True, null=True)
    image = CropDusterField(
        upload_to="nested/item/%Y/%m",
        sizes=IMAGE_SIZES,
        require_alt_text=True,
        related_name="nested_item_image")
    alt_image = CropDusterField(
        upload_to="nested/item_alt/%Y/%m",
        sizes=ALT_IMAGE_SIZES,
        field_identifier="alt",
        related_name="nested_item_alt_image")

    class Meta:
        ordering = ('position',)
