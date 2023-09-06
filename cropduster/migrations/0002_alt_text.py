from django.db import migrations, models
import cropduster.fields


class Migration(migrations.Migration):

    dependencies = [
        ('cropduster', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='image',
            name='alt_text',
            field=models.TextField(blank=True, default='', verbose_name='Alt Text'),
        ),
    ]
