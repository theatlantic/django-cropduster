# encoding: utf-8
import datetime
from south.db import db
from south.v2 import SchemaMigration
from django.db import models

class Migration(SchemaMigration):

    def forwards(self, orm):
        
        # Adding unique constraint on 'Crop', fields ['image', 'size']
        db.create_unique('cropduster_crop', ['image_id', 'size_id'])

        # Adding field 'Size.create_on_request'
        db.add_column('cropduster_size', 'create_on_request', self.gf('django.db.models.fields.BooleanField')(default=False), keep_default=False)

        # Changing field 'Size.auto_size'
        db.alter_column('cropduster_size', 'auto_size', self.gf('django.db.models.fields.PositiveIntegerField')())


    def backwards(self, orm):
        
        # Removing unique constraint on 'Crop', fields ['image', 'size']
        db.delete_unique('cropduster_crop', ['image_id', 'size_id'])

        # Deleting field 'Size.create_on_request'
        db.delete_column('cropduster_size', 'create_on_request')

        # Changing field 'Size.auto_size'
        db.alter_column('cropduster_size', 'auto_size', self.gf('django.db.models.fields.BooleanField')())


    models = {
        'cropduster.crop': {
            'Meta': {'unique_together': "(('size', 'image'),)", 'object_name': 'Crop'},
            'crop_h': ('django.db.models.fields.PositiveIntegerField', [], {'default': '0', 'null': 'True', 'blank': 'True'}),
            'crop_w': ('django.db.models.fields.PositiveIntegerField', [], {'default': '0', 'null': 'True', 'blank': 'True'}),
            'crop_x': ('django.db.models.fields.PositiveIntegerField', [], {'default': '0', 'null': 'True', 'blank': 'True'}),
            'crop_y': ('django.db.models.fields.PositiveIntegerField', [], {'default': '0', 'null': 'True', 'blank': 'True'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'image': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'images'", 'to': "orm['cropduster.Image']"}),
            'size': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'size'", 'to': "orm['cropduster.Size']"})
        },
        'cropduster.image': {
            'Meta': {'object_name': 'Image'},
            'attribution': ('django.db.models.fields.CharField', [], {'max_length': '255', 'null': 'True', 'blank': 'True'}),
            'caption': ('django.db.models.fields.CharField', [], {'max_length': '255', 'null': 'True', 'blank': 'True'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'image': ('django.db.models.fields.files.ImageField', [], {'max_length': '255', 'db_index': 'True'}),
            'size_set': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['cropduster.SizeSet']"})
        },
        'cropduster.size': {
            'Meta': {'object_name': 'Size'},
            'aspect_ratio': ('django.db.models.fields.FloatField', [], {'default': '1'}),
            'auto_size': ('django.db.models.fields.PositiveIntegerField', [], {'default': '0'}),
            'create_on_request': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'height': ('django.db.models.fields.PositiveIntegerField', [], {'null': 'True', 'blank': 'True'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '255', 'db_index': 'True'}),
            'size_set': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['cropduster.SizeSet']"}),
            'slug': ('django.db.models.fields.SlugField', [], {'max_length': '50', 'db_index': 'True'}),
            'width': ('django.db.models.fields.PositiveIntegerField', [], {'null': 'True', 'blank': 'True'})
        },
        'cropduster.sizeset': {
            'Meta': {'object_name': 'SizeSet'},
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '255', 'db_index': 'True'}),
            'slug': ('django.db.models.fields.SlugField', [], {'max_length': '50', 'db_index': 'True'})
        }
    }

    complete_apps = ['cropduster']
