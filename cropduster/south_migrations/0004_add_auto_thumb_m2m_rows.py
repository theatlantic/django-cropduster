# encoding: utf-8
import datetime
from south.db import db
from south.v2 import DataMigration
from django.db import models

class Migration(DataMigration):
    
    def forwards(self, orm):
        if db.dry_run:
            return

        Thumb = orm['cropduster.Thumb']
        Image = orm['cropduster.Image']
        M2M = Image.thumbs.through

        auto_thumbs = Thumb.objects.filter(reference_thumb__isnull=False)
        for auto_thumb in auto_thumbs:
            images = M2M.objects.filter(thumb_id__exact=auto_thumb.reference_thumb_id)
            if len(images) > 1:
                for image in images[1:]:
                    image.delete()
            try:
                thumb_image = images[0]
            except IndexError:
                pass
            else:
                auto_m2m, created = M2M.objects.get_or_create(thumb=auto_thumb, image=thumb_image.image)

    def backwards(self, orm):
        "Write your backwards methods here."
    
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
            'content_type': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['contenttypes.ContentType']"}),
            'date_created': ('django.db.models.fields.DateTimeField', [], {'auto_now_add': 'True', 'blank': 'True'}),
            'date_modified': ('django.db.models.fields.DateTimeField', [], {'auto_now': 'True', 'blank': 'True'}),
            'height': ('django.db.models.fields.PositiveIntegerField', [], {'null': 'True', 'blank': 'True'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'image': ('django.db.models.fields.files.ImageField', [], {'max_length': '100', 'db_column': "'path'", 'db_index': 'True'}),
            'object_id': ('django.db.models.fields.PositiveIntegerField', [], {'null': 'True', 'blank': 'True'}),
            'prev_object_id': ('django.db.models.fields.PositiveIntegerField', [], {'null': 'True', 'blank': 'True'}),
            'thumbs': ('cropduster.fields.CropDusterThumbField', [], {'blank': 'True', 'related_name': "'image_set'", 'null': 'True', 'symmetrical': 'False', 'to': "orm['cropduster.Thumb']"}),
            'width': ('django.db.models.fields.PositiveIntegerField', [], {'null': 'True', 'blank': 'True'})
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
            'name': ('django.db.models.fields.CharField', [], {'max_length': '255', 'db_index': 'True'}),
            'reference_thumb': ('django.db.models.fields.related.ForeignKey', [], {'blank': 'True', 'related_name': "'auto_set'", 'null': 'True', 'to': "orm['cropduster.Thumb']"}),
            'width': ('django.db.models.fields.PositiveIntegerField', [], {'default': '0', 'null': 'True', 'blank': 'True'})
        }
    }
    
    complete_apps = ['cropduster']
