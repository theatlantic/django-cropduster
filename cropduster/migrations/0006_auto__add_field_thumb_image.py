# encoding: utf-8
import datetime
from south.db import db
from south.v2 import SchemaMigration
from django.db import models


class Migration(SchemaMigration):

    def forwards(self, orm):
        # Adding field 'Thumb.image'
        db.add_column('cropduster4_thumb', 'image', self.gf('django.db.models.fields.related.ForeignKey')(blank=True, related_name='+', null=True, to=orm['cropduster.Image']), keep_default=False)
        if not db.dry_run:
            Thumb = orm['cropduster.thumb']
            thumbs = Thumb.objects.filter(image_id__isnull=True)
            if thumbs.count() > 5000:
                print ("\n"
                    " ! There are too many cropduster4_thumb rows to migrate in South.\n\n"
                    " ! You will need to manually migrate the many-to-many table.\n")
                return

            for thumb in thumbs:
                try:
                    image = thumb.image_set.all()[0]
                except IndexError:
                    pass
                else:
                    thumb.image_id = image.pk
                    thumb.save()


    def backwards(self, orm):
        # Deleting field 'Thumb.image'
        db.delete_column('cropduster4_thumb', 'image_id')

    models = {
        'contenttypes.contenttype': {
            'Meta': {'unique_together': "(('app_label', 'model'),)", 'object_name': 'ContentType', 'db_table': "'django_content_type'"},
            'app_label': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'model': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '100'})
        },
        'cropduster.image': {
            'Meta': {'unique_together': "(('content_type', 'object_id', 'prev_object_id'),)", 'object_name': 'Image', 'db_table': "'cropduster4_image'"},
            'attribution': ('django.db.models.fields.CharField', [], {'max_length': '255', 'null': 'True', 'blank': 'True'}),
            'attribution_link': ('django.db.models.fields.URLField', [], {'max_length': '255', 'null': 'True', 'blank': 'True'}),
            'caption': ('django.db.models.fields.CharField', [], {'max_length': '255', 'null': 'True', 'blank': 'True'}),
            'content_type': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['contenttypes.ContentType']"}),
            'date_created': ('django.db.models.fields.DateTimeField', [], {'auto_now_add': 'True', 'blank': 'True'}),
            'date_modified': ('django.db.models.fields.DateTimeField', [], {'auto_now': 'True', 'blank': 'True'}),
            'height': ('django.db.models.fields.PositiveIntegerField', [], {'null': 'True', 'blank': 'True'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'image': ('django.db.models.fields.files.ImageField', [], {'max_length': '100', 'db_column': "'path'", 'db_index': 'True'}),
            'object_id': ('django.db.models.fields.PositiveIntegerField', [], {'null': 'True', 'blank': 'True'}),
            'prev_object_id': ('django.db.models.fields.PositiveIntegerField', [], {'null': 'True', 'blank': 'True'}),
            'width': ('django.db.models.fields.PositiveIntegerField', [], {'null': 'True', 'blank': 'True'}),
            '_thumbs': ('cropduster.fields.CropDusterThumbField', [], {'blank': 'True', 'related_name': "'image_set'", 'null': 'True', 'symmetrical': 'False', 'to': "orm['cropduster.Thumb']", 'through': "orm['cropduster.ImageThumbs']"}),
        },
        'cropduster.imagethumbs': {
            'Meta': {'object_name': 'ImageThumbs', 'db_table': "'cropduster4_image_thumbs'"},
            'image': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['cropduster.Image']"}),
            'thumb': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['cropduster.Thumb']"}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
        },
        'cropduster.standaloneimage': {
            'Meta': {'object_name': 'StandaloneImage', 'db_table': "'cropduster4_standaloneimage'"},
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'image': ('cropduster.fields.CropDusterField', [], {'to': "orm['cropduster.Image']", 'max_length': '100', 'sizes': "[{'max_w': None, 'retina': 0, 'min_h': 1, 'name': 'crop', 'w': None, 'h': None, 'min_w': 1, '__type__': 'Size', 'max_h': None, 'label': u'Crop'}]"}),
            'md5': ('django.db.models.fields.CharField', [], {'max_length': '32'})
        },
        'cropduster.thumb': {
            'Meta': {'object_name': 'Thumb', 'db_table': "'cropduster4_thumb'"},
            'crop_h': ('django.db.models.fields.PositiveIntegerField', [], {'null': 'True', 'blank': 'True'}),
            'crop_w': ('django.db.models.fields.PositiveIntegerField', [], {'null': 'True', 'blank': 'True'}),
            'crop_x': ('django.db.models.fields.PositiveIntegerField', [], {'null': 'True', 'blank': 'True'}),
            'crop_y': ('django.db.models.fields.PositiveIntegerField', [], {'null': 'True', 'blank': 'True'}),
            'date_modified': ('django.db.models.fields.DateTimeField', [], {'auto_now': 'True', 'blank': 'True'}),
            'height': ('django.db.models.fields.PositiveIntegerField', [], {'default': '0', 'null': 'True', 'blank': 'True'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'image': ('django.db.models.fields.related.ForeignKey', [], {'blank': 'True', 'related_name': "'+'", 'null': 'True', 'to': "orm['cropduster.Image']"}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '255', 'db_index': 'True'}),
            'reference_thumb': ('django.db.models.fields.related.ForeignKey', [], {'blank': 'True', 'related_name': "'auto_set'", 'null': 'True', 'to': "orm['cropduster.Thumb']"}),
            'width': ('django.db.models.fields.PositiveIntegerField', [], {'default': '0', 'null': 'True', 'blank': 'True'})
        }
    }

    complete_apps = ['cropduster']
