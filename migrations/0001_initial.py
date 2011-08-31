# encoding: utf-8
import datetime
from south.db import db
from south.v2 import SchemaMigration
from django.db import models

class Migration(SchemaMigration):
    
    def forwards(self, orm):
        
        # Adding model 'SizeSet'
        db.create_table('cropduster_sizeset', (
            ('slug', self.gf('django.db.models.fields.SlugField')(max_length=50, db_index=True)),
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('name', self.gf('django.db.models.fields.CharField')(max_length=255, db_index=True)),
        ))
        db.send_create_signal('cropduster', ['SizeSet'])

        # Adding model 'Size'
        db.create_table('cropduster_size', (
            ('name', self.gf('django.db.models.fields.CharField')(max_length=255, db_index=True)),
            ('height', self.gf('django.db.models.fields.PositiveIntegerField')(default=0, null=True, blank=True)),
            ('width', self.gf('django.db.models.fields.PositiveIntegerField')(default=0, null=True, blank=True)),
            ('size_set', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['cropduster.SizeSet'])),
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('auto_size', self.gf('django.db.models.fields.BooleanField')(default=False, blank=True)),
            ('slug', self.gf('django.db.models.fields.SlugField')(max_length=50, db_index=True)),
        ))
        db.send_create_signal('cropduster', ['Size'])

        # Adding model 'Crop'
        db.create_table('cropduster_crop', (
            ('image', self.gf('django.db.models.fields.related.ForeignKey')(blank=True, related_name='images', null=True, to=orm['cropduster.Image'])),
            ('crop_h', self.gf('django.db.models.fields.PositiveIntegerField')(default=0, null=True, blank=True)),
            ('crop_x', self.gf('django.db.models.fields.PositiveIntegerField')(default=0, null=True, blank=True)),
            ('crop_w', self.gf('django.db.models.fields.PositiveIntegerField')(default=0, null=True, blank=True)),
            ('crop_y', self.gf('django.db.models.fields.PositiveIntegerField')(default=0, null=True, blank=True)),
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('size', self.gf('django.db.models.fields.related.ForeignKey')(blank=True, related_name='size', null=True, to=orm['cropduster.Size'])),
        ))
        db.send_create_signal('cropduster', ['Crop'])

        # Adding model 'Image'
        db.create_table('cropduster_image', (
            ('image', self.gf('django.db.models.fields.files.ImageField')(max_length=255, db_index=True)),
            ('attribution', self.gf('django.db.models.fields.CharField')(max_length=255, null=True, blank=True)),
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
        ))
        db.send_create_signal('cropduster', ['Image'])

        # Adding M2M table for field sizes on 'Image'
        db.create_table('cropduster_image_sizes', (
            ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True)),
            ('image', models.ForeignKey(orm['cropduster.image'], null=False)),
            ('size', models.ForeignKey(orm['cropduster.size'], null=False))
        ))
        db.create_unique('cropduster_image_sizes', ['image_id', 'size_id'])
    
    
    def backwards(self, orm):
        
        # Deleting model 'SizeSet'
        db.delete_table('cropduster_sizeset')

        # Deleting model 'Size'
        db.delete_table('cropduster_size')

        # Deleting model 'Crop'
        db.delete_table('cropduster_crop')

        # Deleting model 'Image'
        db.delete_table('cropduster_image')

        # Removing M2M table for field sizes on 'Image'
        db.delete_table('cropduster_image_sizes')
    
    
    models = {
        'cropduster.crop': {
            'Meta': {'object_name': 'Crop'},
            'crop_h': ('django.db.models.fields.PositiveIntegerField', [], {'default': '0', 'null': 'True', 'blank': 'True'}),
            'crop_w': ('django.db.models.fields.PositiveIntegerField', [], {'default': '0', 'null': 'True', 'blank': 'True'}),
            'crop_x': ('django.db.models.fields.PositiveIntegerField', [], {'default': '0', 'null': 'True', 'blank': 'True'}),
            'crop_y': ('django.db.models.fields.PositiveIntegerField', [], {'default': '0', 'null': 'True', 'blank': 'True'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'image': ('django.db.models.fields.related.ForeignKey', [], {'blank': 'True', 'related_name': "'images'", 'null': 'True', 'to': "orm['cropduster.Image']"}),
            'size': ('django.db.models.fields.related.ForeignKey', [], {'blank': 'True', 'related_name': "'size'", 'null': 'True', 'to': "orm['cropduster.Size']"})
        },
        'cropduster.image': {
            'Meta': {'object_name': 'Image'},
            'attribution': ('django.db.models.fields.CharField', [], {'max_length': '255', 'null': 'True', 'blank': 'True'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'image': ('django.db.models.fields.files.ImageField', [], {'max_length': '255', 'db_index': 'True'}),
            'sizes': ('django.db.models.fields.related.ManyToManyField', [], {'blank': 'True', 'related_name': "'sizes'", 'null': 'True', 'symmetrical': 'False', 'to': "orm['cropduster.Size']"})
        },
        'cropduster.size': {
            'Meta': {'object_name': 'Size'},
            'auto_size': ('django.db.models.fields.BooleanField', [], {'default': 'False', 'blank': 'True'}),
            'height': ('django.db.models.fields.PositiveIntegerField', [], {'default': '0', 'null': 'True', 'blank': 'True'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '255', 'db_index': 'True'}),
            'size_set': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['cropduster.SizeSet']"}),
            'slug': ('django.db.models.fields.SlugField', [], {'max_length': '50', 'db_index': 'True'}),
            'width': ('django.db.models.fields.PositiveIntegerField', [], {'default': '0', 'null': 'True', 'blank': 'True'})
        },
        'cropduster.sizeset': {
            'Meta': {'object_name': 'SizeSet'},
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '255', 'db_index': 'True'}),
            'slug': ('django.db.models.fields.SlugField', [], {'max_length': '50', 'db_index': 'True'})
        }
    }
    
    complete_apps = ['cropduster']
