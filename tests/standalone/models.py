from django.db import models

from ckeditor.fields import RichTextField


class StandaloneArticle(models.Model):
    content = RichTextField(blank=True, config_name='default')
