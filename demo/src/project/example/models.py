from django.db import models

from cropduster.models import CropDusterField, Size
from cropduster.resizing import SizeAlias


def get_video_sizes(instance=None, related=None):
    """Callable ``sizes`` whose dimensions depend on the parent instance.

    The still is scaled to the video's own aspect ratio, and a fixed default
    is used when the field is rendered without an instance (the add form).
    """
    still_w, still_h = (620, 352)
    if instance is not None:
        video_w = getattr(instance, "video_width", None)
        video_h = getattr(instance, "video_height", None)
        if video_w and video_h:
            still_w = min(video_w, 620)
            still_h = int(round(still_w * video_h / video_w))
    return [
        Size(
            "still",
            w=still_w,
            h=still_h,
            auto=[
                Size("still_thumb", w=110, h=90),
            ],
        ),
        Size("square", w=500, h=500),
        SizeAlias("app_square", to="square"),
    ]


class Article(models.Model):
    LEAD_IMAGE_SIZES = [
        Size("main", w=600, h=480, auto=[Size("thumb", w=110, h=90)]),
        Size("no_height", w=600),
    ]
    ALT_IMAGE_SIZES = [
        Size("wide", w=600, h=300),
        SizeAlias("promo", to="wide"),
    ]

    title = models.CharField(max_length=255)
    lead_image = CropDusterField(
        upload_to="img/articles/%Y",
        sizes=LEAD_IMAGE_SIZES,
        related_name="example_article_lead_image",
    )
    alt_image = CropDusterField(
        upload_to="img/articles/alt/%Y",
        sizes=ALT_IMAGE_SIZES,
        field_identifier="alt",
        require_alt_text=True,
        related_name="example_article_alt_image",
    )

    def __str__(self):
        return self.title


class Video(models.Model):
    title = models.CharField(max_length=255)
    video_width = models.PositiveIntegerField(blank=True, null=True)
    video_height = models.PositiveIntegerField(blank=True, null=True)
    still = CropDusterField(
        upload_to="img/videos/%Y",
        sizes=get_video_sizes,
        related_name="example_video_still",
    )

    def __str__(self):
        return self.title


class Gallery(models.Model):
    title = models.CharField(max_length=255)

    class Meta:
        verbose_name_plural = "galleries"

    def __str__(self):
        return self.title


class Photo(models.Model):
    PHOTO_SIZES = [
        Size("main", w=600, h=400, auto=[Size("thumb", w=110, h=90)]),
    ]

    gallery = models.ForeignKey(Gallery, related_name="photos", on_delete=models.CASCADE)
    position = models.PositiveIntegerField(default=0)
    image = CropDusterField(
        upload_to="img/galleries/%Y",
        sizes=PHOTO_SIZES,
        related_name="example_photo_image",
    )
    caption = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ["position"]

    def __str__(self):
        return self.caption or "Photo %s" % self.pk


class Page(models.Model):
    title = models.CharField(max_length=255)

    def __str__(self):
        return self.title


class PageSection(models.Model):
    page = models.ForeignKey(Page, related_name="sections", on_delete=models.CASCADE)
    title = models.CharField(max_length=255, blank=True, default="")
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["position"]

    def __str__(self):
        return self.title or "Section %s" % self.pk


class PageItem(models.Model):
    ITEM_SIZES = [
        Size("main", w=600, h=400, auto=[Size("thumb", w=110, h=90)]),
    ]

    section = models.ForeignKey(
        PageSection, related_name="items", on_delete=models.CASCADE
    )
    title = models.CharField(max_length=255, blank=True, default="")
    position = models.PositiveIntegerField(default=0)
    image = CropDusterField(
        upload_to="img/pages/%Y",
        sizes=ITEM_SIZES,
        related_name="example_pageitem_image",
    )

    class Meta:
        ordering = ["position"]

    def __str__(self):
        return self.title or "Item %s" % self.pk
