# Generated by Django 4.2.5 on 2023-11-01 20:28

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation_service', '0006_specificationtemplate_template_last_modified'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='specificationtemplate',
            name='unique_template_idx',
        ),
        migrations.AddConstraint(
            model_name='specificationtemplate',
            constraint=models.UniqueConstraint(fields=('template_name',), name='unique_template_idx'),
        ),
    ]