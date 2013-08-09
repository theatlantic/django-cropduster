# encoding: utf-8
import datetime
from south.db import db
from south.v2 import SchemaMigration
from django.db import models

class Migration(SchemaMigration):
    
    def forwards(self, orm):
        
        # Adding model 'Thumb'
        db.create_table('cropduster4_thumb', (
            ('width', self.gf('django.db.models.fields.PositiveIntegerField')(default=0, null=True, blank=True)),
            ('height', self.gf('django.db.models.fields.PositiveIntegerField')(default=0, null=True, blank=True)),
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('name', self.gf('django.db.models.fields.CharField')(max_length=255, db_index=True)),
        ))
        db.send_create_signal('cropduster', ['Thumb'])

        # Adding model 'Image'
        db.create_table('cropduster4_image', (
            ('attribution', self.gf('django.db.models.fields.CharField')(max_length=255, null=True, blank=True)),
            ('_extension', self.gf('django.db.models.fields.CharField')(max_length=4, db_column='extension')),
            ('crop_h', self.gf('django.db.models.fields.PositiveIntegerField')(default=0, null=True, blank=True)),
            ('object_id', self.gf('django.db.models.fields.PositiveIntegerField')()),
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('crop_w', self.gf('django.db.models.fields.PositiveIntegerField')(default=0, null=True, blank=True)),
            ('content_type', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['contenttypes.ContentType'])),
            ('path', self.gf('django.db.models.fields.CharField')(max_length=255, db_index=True)),
            ('crop_y', self.gf('django.db.models.fields.PositiveIntegerField')(default=0, null=True, blank=True)),
            ('crop_x', self.gf('django.db.models.fields.PositiveIntegerField')(default=0, null=True, blank=True)),
        ))
        db.send_create_signal('cropduster', ['Image'])

        # Adding unique constraint on 'Image', fields ['content_type', 'object_id']
        db.create_unique('cropduster4_image', ['content_type_id', 'object_id'])

        # Adding M2M table for field thumbs on 'Image'
        db.create_table('cropduster4_image_thumbs', (
            ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True)),
            ('image', models.ForeignKey(orm['cropduster.image'], null=False)),
            ('thumb', models.ForeignKey(orm['cropduster.thumb'], null=False))
        ))
        db.create_unique('cropduster4_image_thumbs', ['image_id', 'thumb_id'])
    
    
    def backwards(self, orm):
        
        # Deleting model 'Thumb'
        db.delete_table('cropduster4_thumb')

        # Deleting model 'Image'
        db.delete_table('cropduster4_image')

        # Removing unique constraint on 'Image', fields ['content_type', 'object_id']
        db.delete_unique('cropduster4_image', ['content_type_id', 'object_id'])

        # Removing M2M table for field thumbs on 'Image'
        db.delete_table('cropduster4_image_thumbs')
    
    
    models = {
        'contenttypes.contenttype': {
            'Meta': {'unique_together': "(('app_label', 'model'),)", 'object_name': 'ContentType', 'db_table': "'django_content_type'"},
            'app_label': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'model': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '100'})
        },
        'cropduster.image': {
            'Meta': {'unique_together': "(('content_type', 'object_id'),)", 'object_name': 'Image', 'db_table': "'cropduster4_image'"},
            '_extension': ('django.db.models.fields.CharField', [], {'max_length': '4', 'db_column': "'extension'"}),
            'attribution': ('django.db.models.fields.CharField', [], {'max_length': '255', 'null': 'True', 'blank': 'True'}),
            'content_type': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['contenttypes.ContentType']"}),
            'crop_h': ('django.db.models.fields.PositiveIntegerField', [], {'default': '0', 'null': 'True', 'blank': 'True'}),
            'crop_w': ('django.db.models.fields.PositiveIntegerField', [], {'default': '0', 'null': 'True', 'blank': 'True'}),
            'crop_x': ('django.db.models.fields.PositiveIntegerField', [], {'default': '0', 'null': 'True', 'blank': 'True'}),
            'crop_y': ('django.db.models.fields.PositiveIntegerField', [], {'default': '0', 'null': 'True', 'blank': 'True'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'object_id': ('django.db.models.fields.PositiveIntegerField', [], {}),
            'path': ('django.db.models.fields.CharField', [], {'max_length': '255', 'db_index': 'True'}),
            'thumbs': ('django.db.models.fields.related.ManyToManyField', [], {'blank': 'True', 'related_name': "'thumbs'", 'null': 'True', 'symmetrical': 'False', 'to': "orm['cropduster.Thumb']"})
        },
        'cropduster.thumb': {
            'Meta': {'object_name': 'Thumb', 'db_table': "'cropduster4_thumb'"},
            'height': ('django.db.models.fields.PositiveIntegerField', [], {'default': '0', 'null': 'True', 'blank': 'True'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '255', 'db_index': 'True'}),
            'width': ('django.db.models.fields.PositiveIntegerField', [], {'default': '0', 'null': 'True', 'blank': 'True'})
        }
    }
    
    complete_apps = ['cropduster']
