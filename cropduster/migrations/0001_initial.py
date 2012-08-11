# encoding: utf-8
import datetime
from south.db import db
from south.v2 import SchemaMigration
from django.db import models

class Migration(SchemaMigration):
    
    def forwards(self, orm):
        
        # Adding model 'Image'
        db.create_table('cropduster_image', (
            ('crop_h', self.gf('django.db.models.fields.PositiveIntegerField')(default=0, null=True, blank=True)),
            ('crop_x', self.gf('django.db.models.fields.PositiveIntegerField')(default=0, null=True, blank=True)),
            ('crop_w', self.gf('django.db.models.fields.PositiveIntegerField')(default=0, null=True, blank=True)),
            ('path', self.gf('django.db.models.fields.CharField')(max_length=255)),
            ('crop_y', self.gf('django.db.models.fields.PositiveIntegerField')(default=0, null=True, blank=True)),
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('default_thumb', self.gf('django.db.models.fields.CharField')(max_length=255)),
        ))
        db.send_create_signal('cropduster', ['Image'])

        # Adding M2M table for field thumbs on 'Image'
        db.create_table('cropduster_image_thumbs', (
            ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True)),
            ('image', models.ForeignKey(orm['cropduster.image'], null=False)),
            ('thumb', models.ForeignKey(orm['cropduster.thumb'], null=False))
        ))
        db.create_unique('cropduster_image_thumbs', ['image_id', 'thumb_id'])

        # Adding model 'Thumb'
        db.create_table('cropduster_thumb', (
            ('width', self.gf('django.db.models.fields.PositiveIntegerField')(default=0, null=True, blank=True)),
            ('height', self.gf('django.db.models.fields.PositiveIntegerField')(default=0, null=True, blank=True)),
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('name', self.gf('django.db.models.fields.CharField')(max_length=255, db_index=True)),
        ))
        db.send_create_signal('cropduster', ['Thumb'])
    
    
    def backwards(self, orm):
        
        # Deleting model 'Image'
        db.delete_table('cropduster_image')

        # Removing M2M table for field thumbs on 'Image'
        db.delete_table('cropduster_image_thumbs')

        # Deleting model 'Thumb'
        db.delete_table('cropduster_thumb')
    
    
    models = {
        'cropduster.image': {
            'Meta': {'object_name': 'Image'},
            'crop_h': ('django.db.models.fields.PositiveIntegerField', [], {'default': '0', 'null': 'True', 'blank': 'True'}),
            'crop_w': ('django.db.models.fields.PositiveIntegerField', [], {'default': '0', 'null': 'True', 'blank': 'True'}),
            'crop_x': ('django.db.models.fields.PositiveIntegerField', [], {'default': '0', 'null': 'True', 'blank': 'True'}),
            'crop_y': ('django.db.models.fields.PositiveIntegerField', [], {'default': '0', 'null': 'True', 'blank': 'True'}),
            'default_thumb': ('django.db.models.fields.CharField', [], {'max_length': '255'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'path': ('django.db.models.fields.CharField', [], {'max_length': '255'}),
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
