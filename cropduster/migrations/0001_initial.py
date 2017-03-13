import cropduster.fields
import cropduster.models
import django
from django.db import migrations, models
import django.db.models.deletion
import cropduster.settings


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
    ]

    operations = [
        migrations.CreateModel(
            name='Image',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('object_id', models.PositiveIntegerField(null=True, blank=True)),
                ('field_identifier', models.SlugField(blank=True, default='')),
                ('prev_object_id', models.PositiveIntegerField(null=True, blank=True)),
                ('width', models.PositiveIntegerField(null=True, blank=True)),
                ('height', models.PositiveIntegerField(null=True, blank=True)),
                ('image', cropduster.fields.CropDusterSimpleImageField(db_column='path', db_index=True, height_field='height', storage=cropduster.models.StrFileSystemStorage(), upload_to=cropduster.models.generate_filename, width_field='width')),
                ('date_created', models.DateTimeField(auto_now_add=True)),
                ('date_modified', models.DateTimeField(auto_now=True)),
                ('attribution', models.CharField(max_length=255, null=True, blank=True)),
                ('attribution_link', models.URLField(max_length=255, null=True, blank=True)),
                ('caption', models.TextField(null=True, blank=True)),
                ('content_type', models.ForeignKey(to='contenttypes.ContentType', on_delete=models.CASCADE)),
            ],
            options={
                'db_table': '%s_image' % cropduster.settings.CROPDUSTER_DB_PREFIX,
            },
        ),
        migrations.CreateModel(
            name='StandaloneImage',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('md5', models.CharField(max_length=32)),
                ('image', cropduster.fields.CropDusterImageField(blank=True, db_column='image', default='', upload_to='')),
            ],
            options={
                'db_table': '%s_standaloneimage' % cropduster.settings.CROPDUSTER_DB_PREFIX,
            },
        ),
        migrations.CreateModel(
            name='Thumb',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=255, db_index=True)),
                ('width', models.PositiveIntegerField(default=0, null=True, blank=True)),
                ('height', models.PositiveIntegerField(default=0, null=True, blank=True)),
                ('crop_x', models.PositiveIntegerField(null=True, blank=True)),
                ('crop_y', models.PositiveIntegerField(null=True, blank=True)),
                ('crop_w', models.PositiveIntegerField(null=True, blank=True)),
                ('crop_h', models.PositiveIntegerField(null=True, blank=True)),
                ('date_modified', models.DateTimeField(auto_now=True)),
                ('image', models.ForeignKey(related_name='+', to='cropduster.Image', blank=True, null=True, on_delete=models.CASCADE)),
                ('reference_thumb', models.ForeignKey(related_name='auto_set', blank=True, to='cropduster.Thumb', null=True, on_delete=models.CASCADE)),
            ],
            options={
                'db_table': '%s_thumb' % cropduster.settings.CROPDUSTER_DB_PREFIX,
            },
        ),
    ] + ([] if django.VERSION < (1, 9) else [
        migrations.AddField(
            model_name='image',
            name='thumbs',
            field=cropduster.fields.ReverseForeignRelation(blank=True, field_name='image', serialize=False, to='cropduster.Thumb', is_migration=True),
        ),
    ]) + [
        migrations.AlterUniqueTogether(
            name='image',
            unique_together=set([('content_type', 'object_id', 'field_identifier')]),
        ),
    ]
