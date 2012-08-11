# encoding: utf-8
import datetime
from south.db import db
from south.v2 import SchemaMigration
from django.db import models

class Migration(SchemaMigration):
    
    def forwards(self, orm):
        
        # Adding unique constraint on 'Image', fields ['object_id', 'content_type']
        db.create_unique('cropduster_image', ['object_id', 'content_type_id'])
    
    
    def backwards(self, orm):
        
        # Removing unique constraint on 'Image', fields ['object_id', 'content_type']
        db.delete_unique('cropduster_image', ['object_id', 'content_type_id'])
    
    
    models = {
        'contenttypes.contenttype': {
            'Meta': {'unique_together': "(('app_label', 'model'),)", 'object_name': 'ContentType', 'db_table': "'django_content_type'"},
            'app_label': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'model': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '100'})
        },
        'cropduster.image': {
            'Meta': {'unique_together': "(('content_type', 'object_id'),)", 'object_name': 'Image'},
            '_extension': ('django.db.models.fields.CharField', [], {'max_length': '4', 'db_column': "'extension'"}),
            'attribution': ('django.db.models.fields.CharField', [], {'max_length': '255', 'null': 'True', 'blank': 'True'}),
            'content_type': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['contenttypes.ContentType']"}),
            'crop_h': ('django.db.models.fields.PositiveIntegerField', [], {'default': '0', 'null': 'True', 'blank': 'True'}),
            'crop_w': ('django.db.models.fields.PositiveIntegerField', [], {'default': '0', 'null': 'True', 'blank': 'True'}),
            'crop_x': ('django.db.models.fields.PositiveIntegerField', [], {'default': '0', 'null': 'True', 'blank': 'True'}),
            'crop_y': ('django.db.models.fields.PositiveIntegerField', [], {'default': '0', 'null': 'True', 'blank': 'True'}),
            'default_thumb': ('django.db.models.fields.CharField', [], {'max_length': '255'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'object_id': ('django.db.models.fields.PositiveIntegerField', [], {}),
            'path': ('django.db.models.fields.CharField', [], {'max_length': '255', 'db_index': 'True'}),
            'thumbs': ('django.db.models.fields.related.ManyToManyField', [], {'blank': 'True', 'related_name': "'thumbs'", 'null': 'True', 'symmetrical': 'False', 'to': "orm['cropduster.Thumb']"})
        },
        'cropduster.thumb': {
            'Meta': {'object_name': 'Thumb'},
            'height': ('django.db.models.fields.PositiveIntegerField', [], {'default': '0', 'null': 'True', 'blank': 'True'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '255', 'db_index': 'True'}),
            'width': ('django.db.models.fields.PositiveIntegerField', [], {'default': '0', 'null': 'True', 'blank': 'True'})
        }
    }
    
    complete_apps = ['cropduster']
